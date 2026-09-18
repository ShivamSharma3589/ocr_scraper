"""
Extract LookFantastic's live Google ad campaigns from the Ads Transparency Center.

The SerpApi list endpoint returns creative IDs and dates but never the ad copy,
so the text is recovered from whichever source a creative actually carries:

  1. `link`  -> a gzipped protobuf blob in the URL's `overlay` param. Exact text.
  2. `image` -> a rendered screenshot of the ad. OCR'd, headline and description
                separated by text colour (Google renders headlines in blue).
  3. image / video formats -> no ad copy exists anywhere upstream. Only the
     reseller identity and landing URLs are recorded.

The `google_ads_transparency_center_ad_details` engine is deliberately not used:
it was tested against every creative and returns no ad copy at all.

Each run is a self-contained snapshot stamped with its start time:

    output/img/<RUN_ID>/              downloaded creative images
    output/transparency_data/<RUN_ID>.json    every creative plus extracted copy
    output/filtered_brands/<RUN_ID>.json      creatives matching BRAND_FILTER

Usage:
    python extract.py
"""

import base64
import gzip
import io
import json
import os
import re
import socket
import time
import unicodedata
import urllib.parse
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import pytesseract
import requests
from PIL import Image

from config import SERP_API_KEY


# --------------------------------------------------------------- configuration

# Date window to query. `end_date` is exclusive, so these two values mean
# "ads shown on 17 Sep 2026". Bump both to move the window.
START_DATE = "20260917"
END_DATE = "20260918"

LIMIT = None            # cap on creatives processed; None means the whole window
WORKERS = 8             # parallel downloads + OCR
DOWNLOAD_RETRIES = 3    # attempts per image before giving up

# Brands to pull out into output/filtered_brands/. Headlines are normalised
# before matching (accents stripped, punctuation flattened, lowercased), so the
# patterns below only need to absorb OCR confusions - mainly l/i/1 and q/g.
# Set to {} to skip the filtering step entirely.
BRANDS = {
    "Clinique":     r"\bcl[il1]n[il1][qg]ue\b",
    "MAC":          r"\bm\s?a\s?c\b",
    "Tom Ford":     r"\btom\s+f[o0]rd\b",
    "Jo Malone":    r"\bj[o0]\s+mal[o0]ne\b",
    "Bobbi Brown":  r"\bb[o0]bb[il1]e?\s+br[o0]wne?\b",
    "Estee Lauder": r"\beste[e3]?\s+lauder\b",
    "Too Faced":    r"\bt[o0]{2}\s+face[db]?\b",
}

SERPAPI_URL = "https://serpapi.com/search.json"
IMAGE_HOST = "tpc.googlesyndication.com"

LIST_PARAMS = {
    "engine": "google_ads_transparency_center",
    "text": "lookfantastic.com",
    "region": "2826",          # 2826 = United Kingdom
    "start_date": START_DATE,
    "end_date": END_DATE,
    "num": 100,                # page size; the API caps this at 100
}

IMAGE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
    ),
    "Referer": "https://adstransparency.google.com/",
}

RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")

OUTPUT_DIR = "output"
IMAGE_DIR = os.path.join(OUTPUT_DIR, "img", RUN_ID)
DATA_DIR = os.path.join(OUTPUT_DIR, "transparency_data")
FILTERED_DIR = os.path.join(OUTPUT_DIR, "filtered_brands")
RESULTS_FILE = os.path.join(DATA_DIR, f"{RUN_ID}.json")
FILTERED_FILE = os.path.join(FILTERED_DIR, f"{RUN_ID}.json")


# --------------------------------------------------------------- preflight

def check_image_host():
    """Return a warning if the image CDN is unreachable, else None.

    Ad blockers commonly sinkhole googlesyndication.com, which would otherwise
    surface as thousands of identical connection errors deep into a run.
    """
    try:
        address = socket.gethostbyname(IMAGE_HOST)
    except OSError:
        return f"{IMAGE_HOST} does not resolve"

    if address in ("0.0.0.0", "127.0.0.1", "::1"):
        return f"{IMAGE_HOST} resolves to {address} - blocked by a DNS ad blocker"

    return None


# ------------------------------------------------------------ overlay decoding

def _read_varint(buf, index):
    """Read a protobuf varint, returning (value, next_index)."""
    value = shift = 0
    while True:
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7


def _overlay_field(blob, name):
    """Every string stored under a named field in the overlay blob.

    Fields are laid out as: \\n <len> <name> \\x12 <len> \\n <len> <value>
    """
    key = b"\n" + bytes([len(name)]) + name
    found, position = [], blob.find(key)

    while position != -1:
        index = position + len(key)
        if blob[index : index + 1] == b"\x12":
            index += 1
            _, index = _read_varint(blob, index)      # wrapper message length
            if blob[index : index + 1] == b"\n":
                index += 1
                length, index = _read_varint(blob, index)
                found.append(blob[index : index + length].decode("utf-8", "replace"))
        position = blob.find(key, position + 1)

    return found


def decode_overlay(link):
    """Return (param_name, decompressed_blob) from a creative preview link."""
    query = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)

    for key in ("overlay", "assets"):
        if key in query:
            encoded = query[key][0].lstrip("=")
            padded = encoded + "=" * (-len(encoded) % 4)
            return key, gzip.decompress(base64.urlsafe_b64decode(padded))

    return None, None


# ------------------------------------------------------- source 1: overlay

def from_overlay(link):
    """Exact ad copy for text creatives that expose a preview link."""
    _, blob = decode_overlay(link)
    if not blob:
        return None

    headlines = _overlay_field(blob, b"headline")
    if not headlines:
        return None

    descriptions = _overlay_field(blob, b"description")
    display_urls = _overlay_field(blob, b"visurl")

    return {
        "source": "overlay",
        "headline": headlines[0],
        "description": descriptions[0] if descriptions else None,
        "display_url": display_urls[0] if display_urls else None,
        "headline_variants": headlines[1:],
        "sitelinks": [],
    }


# ----------------------------------------------------------- source 2: OCR

# Lines that end the description: seller-rating and policy widgets.
STOP_RE = re.compile(r"^(sponsored|rating for|return policy|most items|\d[.,]\d\s)", re.I)


def _is_blue(rgb):
    """Google renders ad headlines and sitelink titles in blue, body text in grey."""
    red, green, blue = rgb
    return blue - max(red, green) > 25 and blue > 80


def _ink_colour(image, box):
    """Average colour of the darkest quarter of pixels in a word box.

    Averaging every pixel would wash the text colour out with background, so
    only the darkest pixels - the glyph strokes themselves - are sampled.
    """
    crop = image.crop(box).convert("RGB")
    pixels = list(crop.getdata())
    if not pixels:
        return (0, 0, 0)

    ink = sorted(pixels, key=sum)[: max(1, len(pixels) // 4)]
    return tuple(sum(channel) // len(ink) for channel in zip(*ink))


def _ocr_lines(image):
    """OCR the image into lines, each flagged as blue (heading) or not."""
    data = pytesseract.image_to_data(
        image, config="--psm 6", output_type=pytesseract.Output.DICT
    )

    grouped = OrderedDict()
    for i, text in enumerate(data["text"]):
        if not text.strip() or int(data["conf"][i]) < 40:
            continue

        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        box = (
            data["left"][i],
            data["top"][i],
            data["left"][i] + data["width"][i],
            data["top"][i] + data["height"][i],
        )
        grouped.setdefault(key, []).append((text, box))

    lines = []
    for words in grouped.values():
        blues = sum(1 for _, box in words if _is_blue(_ink_colour(image, box)))
        lines.append({
            "text": " ".join(word for word, _ in words),
            "blue": blues > len(words) / 2,
        })

    return lines


def from_ocr(image_bytes):
    """Read headline, description and sitelinks out of a rendered ad image."""
    image = Image.open(io.BytesIO(image_bytes))
    # Doubling the size measurably sharpens tesseract on these small renders.
    image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)

    lines = _ocr_lines(image)
    blue_at = [i for i, line in enumerate(lines) if line["blue"]]
    if not blue_at:
        return None

    # The headline is the FIRST contiguous run of blue lines. Sitelink titles
    # further down are blue too, and must not be folded into the headline.
    start = end = blue_at[0]
    while end + 1 < len(lines) and lines[end + 1]["blue"]:
        end += 1

    header = [l["text"] for l in lines[:start] if not STOP_RE.match(l["text"])]
    headline = " ".join(l["text"] for l in lines[start : end + 1])

    # The description runs until the next blue line or a rating/policy widget.
    cursor = end + 1
    description = []
    while cursor < len(lines):
        if lines[cursor]["blue"] or STOP_RE.match(lines[cursor]["text"]):
            break
        description.append(lines[cursor]["text"])
        cursor += 1

    # Anything after that is sitelinks: a blue title plus its grey body lines.
    sitelinks = []
    while cursor < len(lines):
        if not lines[cursor]["blue"]:
            cursor += 1
            continue

        title, cursor = lines[cursor]["text"], cursor + 1
        body = []
        while cursor < len(lines) and not lines[cursor]["blue"]:
            if not STOP_RE.match(lines[cursor]["text"]):
                body.append(lines[cursor]["text"])
            cursor += 1
        sitelinks.append({"title": title, "description": " ".join(body) or None})

    display_url = next((t for t in header if "." in t and " " not in t.strip()), None)

    return {
        "source": "ocr",
        "headline": headline.strip() or None,
        "description": " ".join(description).strip() or None,
        "display_url": display_url,
        "headline_variants": [],
        "sitelinks": sitelinks,
        "raw_text": "\n".join(l["text"] for l in lines),
    }


# ------------------------------------------- source 3: shopping and video

URL_RE = re.compile(rb"https?://[\x20-\x7e]{6,200}")


def from_nontext_creative(ad):
    """Image (shopping) and video creatives carry no headline or description.

    Their overlay holds the comparison-shopping provider and landing URLs, so
    record that rather than pretending ad copy was recovered.
    """
    if not ad.get("link"):
        return None

    param, blob = decode_overlay(ad["link"])
    if not blob:
        return None

    providers = _overlay_field(blob, b"cssDisplayString")

    urls = []
    for match in URL_RE.findall(blob):
        url = re.split(r"[\x00-\x1f(]", match.decode("utf-8", "replace"))[0].rstrip("&")
        if url not in urls:
            urls.append(url)

    is_shopping = ad.get("format") == "image"

    return {
        "source": "shopping" if is_shopping else "video",
        "headline": None,
        "description": None,
        "display_url": None,
        "css_provider": providers[0] if providers else None,
        "landing_urls": urls[:5],
        "overlay_param": param,
        "note": (
            "shopping/PLA creative - no headline or description exists"
            if is_shopping
            else "video creative - no text assets available"
        ),
    }


# ------------------------------------------------------------ offer parsing

PROMO_RE = re.compile(r"\bcode:?\s*([A-Z0-9]{3,15})\b", re.I)
DISCOUNT_RE = re.compile(r"(?:up\s+to\s+)?\d{1,3}%\s*off(?:\s+selected)?", re.I)
EXTRA_RE = re.compile(r"extra\s+\d{1,3}%", re.I)


def parse_offer(copy):
    """Pull promo codes and discounts out of the recovered ad copy."""
    text = " ".join(filter(None, [copy.get("headline"), copy.get("description")]))

    return {
        "promo_codes": sorted({code.upper() for code in PROMO_RE.findall(text)}),
        "discounts": sorted({d.strip() for d in DISCOUNT_RE.findall(text)}),
        "extras": sorted({e.strip() for e in EXTRA_RE.findall(text)}),
    }


# ----------------------------------------------------------------- fetching

def fetch_ads(limit=None):
    """Page through the list engine, de-duplicating creatives by ID."""
    ads = OrderedDict()
    token = None
    page = 0

    while limit is None or len(ads) < limit:
        params = dict(LIST_PARAMS, api_key=SERP_API_KEY)
        if token:
            params["next_page_token"] = token

        response = requests.get(SERPAPI_URL, params=params, timeout=90)
        response.raise_for_status()
        data = response.json()

        if data.get("error"):
            raise RuntimeError(f"SerpApi error: {data['error']}")

        batch = data.get("ad_creatives", [])
        if not batch:
            break

        for ad in batch:
            ads.setdefault(ad["ad_creative_id"], ad)

        page += 1
        print(f"  page {page:3}: +{len(batch):3} -> {len(ads)} unique", flush=True)

        token = data.get("serpapi_pagination", {}).get("next_page_token")
        if not token:
            break

    values = list(ads.values())
    return values if limit is None else values[:limit]


def describe_error(exc):
    """Readable reason for a failed creative, rather than a raw traceback."""
    reasons = {
        requests.exceptions.ConnectionError: "network connection failed",
        requests.exceptions.Timeout: "request timed out",
        requests.exceptions.HTTPError: "server returned an HTTP error",
        requests.exceptions.RequestException: "request failed",
        OSError: "could not write the image to disk",
    }

    for kind, reason in reasons.items():
        if isinstance(exc, kind):
            return f"{reason}: {exc}"

    return f"{type(exc).__name__}: {exc}"


def fetch_image(ad, creative_id):
    """Download a creative image into this run's folder. Always fresh, no cache."""
    last_error = None

    for attempt in range(1, DOWNLOAD_RETRIES + 1):
        try:
            response = requests.get(ad["image"], headers=IMAGE_HEADERS, timeout=30)
            response.raise_for_status()

            path = os.path.join(IMAGE_DIR, f"{creative_id}.png")
            with open(path, "wb") as handle:
                handle.write(response.content)

            return response.content

        except (requests.exceptions.ConnectionError,
                requests.exceptions.Timeout) as exc:
            last_error = exc
            if attempt < DOWNLOAD_RETRIES:
                time.sleep(attempt)      # brief linear backoff

    raise last_error


# ----------------------------------------------------------------- pipeline

def process_ad(ad):
    """Resolve one creative's ad copy. Safe to call concurrently."""
    creative_id = ad["ad_creative_id"]
    copy = None

    try:
        if ad.get("format") in ("image", "video"):
            copy = from_nontext_creative(ad)
            if not copy and ad.get("image"):
                copy = from_ocr(fetch_image(ad, creative_id))

        elif ad.get("link"):
            copy = from_overlay(ad["link"])

        elif ad.get("image"):
            copy = from_ocr(fetch_image(ad, creative_id))

    except Exception as exc:
        copy = {"source": "error", "error": describe_error(exc)}

    if copy is None:
        copy = {"source": "error", "error": "no copy recovered"}

    if copy.get("headline"):
        copy["offer"] = parse_offer(copy)

    ad["ocr_result"] = copy
    return ad


def build_campaigns(ads):
    """Collapse creatives that share a headline into one campaign entry."""
    campaigns = OrderedDict()

    for ad in ads:
        copy = ad["ocr_result"]
        headline = copy.get("headline")
        if not headline:
            continue

        key = re.sub(r"[^a-z0-9]+", " ", headline.lower()).strip()
        entry = campaigns.get(key)

        if entry is None:
            entry = campaigns[key] = {
                "headline": headline,
                "description": copy.get("description"),
                "display_url": copy.get("display_url"),
                "offer": copy.get("offer"),
                "sources": set(),
                "creative_ids": [],
                "creative_count": 0,
                "first_shown": ad["first_shown"],
                "last_shown": ad["last_shown"],
            }

        entry["creative_ids"].append(ad["ad_creative_id"])
        entry["creative_count"] += 1
        entry["sources"].add(copy["source"])
        entry["first_shown"] = min(entry["first_shown"], ad["first_shown"])
        entry["last_shown"] = max(entry["last_shown"], ad["last_shown"])

    for entry in campaigns.values():
        entry["sources"] = sorted(entry["sources"])

    return sorted(campaigns.values(), key=lambda c: -c["creative_count"])


def normalise(text):
    """Flatten text so brand matching survives accents, casing and punctuation.

    "Estee Lauder", "Estée Lauder" and "M.A.C" all collapse to a plain
    lowercase form, leaving the patterns to handle only OCR letter confusions.
    """
    decomposed = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


BRAND_PATTERNS = {name: re.compile(p) for name, p in BRANDS.items()}


def match_brands(copy):
    """Canonical brand names this creative is advertising.

    Only the headline is matched. Descriptions routinely promote a free gift
    from an unrelated brand - "App Exclusive Bobbi Brown Gift" appears under
    Aveda and Color Wow headlines - and matching those would treble the count
    with campaigns that are not for the brand at all.
    """
    text = normalise(copy.get("headline") or "")

    return [name for name, pattern in BRAND_PATTERNS.items() if pattern.search(text)]


def write_filtered(ads):
    """Write creatives mentioning any tracked brand to their own file."""
    if not BRANDS:
        return None, 0, {}

    matched = []
    per_brand = OrderedDict((name, 0) for name in BRANDS)

    for ad in ads:
        hits = match_brands(ad["ocr_result"])
        if not hits:
            continue

        record = dict(ad)
        record["matched_brands"] = hits
        matched.append(record)

        for name in hits:
            per_brand[name] += 1

    payload = {
        "run_id": RUN_ID,
        "brands": list(BRANDS),
        "matched_count": len(matched),
        "per_brand_counts": per_brand,
        "ad_creatives": matched,
    }
    with open(FILTERED_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    return FILTERED_FILE, len(matched), per_brand


# ---------------------------------------------------------------- reporting

def report(ads, campaigns, stats, filtered_path, filtered_count, per_brand):
    print()
    print("=" * 70)
    print("  ".join(f"{name}={count}" for name, count in stats.items()))
    print(f"deduped:   {len(ads)} creatives -> {len(campaigns)} campaigns")
    print(f"results:   {RESULTS_FILE}")
    print(f"images:    {IMAGE_DIR}")
    if filtered_path:
        print(f"filtered:  {filtered_path}  ({filtered_count} matched)")
        hits = ", ".join(f"{n}={c}" for n, c in per_brand.items() if c)
        print(f"  brands:  {hits or 'none of the tracked brands appeared'}")
    print("=" * 70)

    for campaign in campaigns[:40]:
        offer = campaign.get("offer") or {}
        bits = offer.get("promo_codes", []) + offer.get("discounts", [])
        print(f"\n x{campaign['creative_count']} "
              f"[{'/'.join(campaign['sources'])}] {campaign['headline']}")
        if bits:
            print(f"      offer: {', '.join(bits)}")

    if len(campaigns) > 40:
        print(f"\n... and {len(campaigns) - 40} more (see {RESULTS_FILE})")


def main():
    for directory in (IMAGE_DIR, DATA_DIR, FILTERED_DIR):
        os.makedirs(directory, exist_ok=True)

    warning = check_image_host()
    if warning:
        print(f"WARNING: {warning}")
        print("         Image-based creatives cannot be OCR'd until this is "
              "resolved.\n")

    print(f"Run {RUN_ID} - fetching {START_DATE} to {END_DATE}...")
    ads = fetch_ads(LIMIT)
    print(f"Got {len(ads)} creatives "
          f"({sum(1 for a in ads if a.get('image'))} image / "
          f"{sum(1 for a in ads if a.get('link'))} link)\n")

    done = 0
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for _ in pool.map(process_ad, ads):
            done += 1
            if done % 25 == 0 or done == len(ads):
                print(f"  processed {done}/{len(ads)}", flush=True)

    stats = OrderedDict(
        (name, 0) for name in ("overlay", "ocr", "shopping", "video", "error")
    )
    for ad in ads:
        source = ad["ocr_result"]["source"]
        stats[source] = stats.get(source, 0) + 1

    campaigns = build_campaigns(ads)

    payload = {
        "run_id": RUN_ID,
        "start_date": START_DATE,
        "end_date": END_DATE,
        "limit": LIMIT,
        "extraction_stats": stats,
        "campaign_count": len(campaigns),
        "campaigns": campaigns,
        "ad_creatives": ads,
    }
    with open(RESULTS_FILE, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)

    filtered_path, filtered_count, per_brand = write_filtered(ads)
    report(ads, campaigns, stats, filtered_path, filtered_count, per_brand)


if __name__ == "__main__":
    main()
