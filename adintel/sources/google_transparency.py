"""Google Ads Transparency Center via SerpApi.

SerpApi is used rather than SearchAPI because only SerpApi exposes the creative
preview `link`, whose overlay blob yields exact ad text without OCR. Everything
else falls back to downloading the rendered screenshot and reading it.
"""

import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from adintel.config import settings
from adintel.extraction import ocr, overlay
from adintel.logging_setup import get as get_logger
from adintel.sources.base import Creative, to_datetime

PLATFORM = "google_ads"


ERROR_PAGE_RE = re.compile(
    r"that.?s an error|error\s*\d{3}|try again later|that.?s all we know", re.I
)


def is_error_page(copy):
    """Google serves 500/404 pages as images with HTTP 200, so they download
    cleanly and only reveal themselves once read."""
    text = " ".join(filter(None, [copy.get("raw_text"), copy.get("headline")]))
    return bool(text) and bool(ERROR_PAGE_RE.search(text))


def image_host_blocked():
    """Ad blockers sinkhole googlesyndication.com, which would otherwise surface
    as thousands of identical connection errors mid-run."""
    try:
        address = socket.gethostbyname(settings.GOOGLE_IMAGE_HOST)
    except OSError:
        return f"{settings.GOOGLE_IMAGE_HOST} does not resolve"
    if address in ("0.0.0.0", "127.0.0.1", "::1"):
        return f"{settings.GOOGLE_IMAGE_HOST} resolves to {address} (DNS ad blocker)"
    return None


def _download(url, destination):
    last = None
    for attempt in range(1, settings.DOWNLOAD_RETRIES + 1):
        try:
            response = requests.get(url, headers=settings.BROWSER_HEADERS, timeout=30)
            response.raise_for_status()
            with open(destination, "wb") as handle:
                handle.write(response.content)
            return response.content
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as exc:
            last = exc
            if attempt < settings.DOWNLOAD_RETRIES:
                time.sleep(attempt)
    raise last


def fetch(client, retailer, start_date, end_date, limit=None):
    log = get_logger()
    creatives, token, seen = [], None, set()
    page = 0

    log.info(f"fetching {retailer.slug} {start_date} -> {end_date}")

    while True:
        params = {
            "engine": "google_ads_transparency_center",
            "text": retailer.domain,
            "region": "2826" if retailer.region == "GB" else retailer.region,
            "start_date": start_date.strftime("%Y%m%d"),
            "end_date": end_date.strftime("%Y%m%d"),
            "num": settings.PAGE_SIZE,
        }
        if token:
            params["next_page_token"] = token

        data = client.get(params)
        batch = data.get("ad_creatives") or []
        if not batch:
            break

        page += 1
        total = (data.get("search_information") or {}).get("total_results")
        log.info(f"  page {page:3}  +{len(batch):3}"
                 + (f"  (api reports ~{total} available)" if page == 1 and total else ""))

        for ad in batch:
            creative_id = ad.get("ad_creative_id")
            if not creative_id or creative_id in seen:
                continue
            seen.add(creative_id)

            creatives.append(Creative(
                platform=PLATFORM,
                platform_creative_id=creative_id,
                format=ad.get("format"),
                advertiser_id=ad.get("advertiser_id"),
                advertiser_name=ad.get("advertiser"),
                first_shown=to_datetime(ad.get("first_shown")),
                last_shown=to_datetime(ad.get("last_shown")),
                total_days_shown=ad.get("total_days_shown"),
                details_url=ad.get("details_link"),
                media_url=ad.get("image"),
                preview_link=ad.get("link"),
                raw=ad,
            ))
            if limit and len(creatives) >= limit:
                return creatives

        token = (data.get("serpapi_pagination") or {}).get("next_page_token")
        if not token:
            log.info(f"  pagination complete after {page} pages")
            break

    return creatives


def extract_copy(creatives, image_dir, workers=None):
    log = get_logger()
    os.makedirs(image_dir, exist_ok=True)

    needs_image = sum(1 for c in creatives if c.media_url and not c.preview_link)
    log.info(f"extracting copy from {len(creatives)} creatives "
             f"({needs_image} need download + OCR)")
    progress = {"done": 0, "ocr": 0, "overlay": 0, "no_text": 0, "error": 0}
    lock = threading.Lock()

    def resolve(creative):
        try:
            if creative.format in ("image", "video") and creative.preview_link:
                creative.copy = overlay.shopping_copy(
                    creative.preview_link, creative.format == "image"
                )
            elif creative.preview_link:
                creative.copy = overlay.text_copy(creative.preview_link)
                if not creative.copy and not creative.media_url:
                    param, _ = overlay.decode(creative.preview_link)
                    creative.copy = {
                        "extraction_source": "no_text",
                        "note": f"preview carries only an '{param}' blob - no ad copy exists",
                    }

            if not creative.copy and creative.media_url:
                path = os.path.join(image_dir, f"{creative.platform_creative_id}.png")
                for attempt in range(1, 4):
                    blob = _download(creative.media_url, path)
                    creative.copy = ocr.extract(blob)
                    if not creative.copy or not is_error_page(creative.copy):
                        break
                    creative.copy = None
                    time.sleep(attempt)
                else:
                    creative.copy = {
                        "extraction_source": "error",
                        "error": "google served an error page instead of the creative",
                    }
                if creative.copy and creative.copy.get("extraction_source") == "ocr":
                    creative.copy["image_path"] = path

        except Exception as exc:
            creative.copy = {
                "extraction_source": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        if not creative.copy:
            creative.copy = {"extraction_source": "error", "error": "no copy recovered"}

        with lock:
            progress["done"] += 1
            source = creative.copy.get("extraction_source", "error")
            progress[source] = progress.get(source, 0) + 1
            if progress["done"] % 100 == 0 or progress["done"] == len(creatives):
                log.info(f"  {progress['done']}/{len(creatives)}  "
                         f"ocr={progress['ocr']} overlay={progress['overlay']} "
                         f"no_text={progress['no_text']} errors={progress['error']}")
        return creative

    with ThreadPoolExecutor(max_workers=workers or settings.WORKERS) as pool:
        list(pool.map(resolve, creatives))

    log.info("extraction complete")
    return creatives
