"""Google Ads Transparency Center via SerpApi.

SerpApi is used rather than SearchAPI because only SerpApi exposes the creative
preview `link`, whose overlay blob yields exact ad text without OCR. Everything
else falls back to downloading the rendered screenshot and reading it.
"""

import os
import socket
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from adintel.config import settings
from adintel.extraction import ocr, overlay
from adintel.sources.base import Creative, to_datetime

PLATFORM = "google_ads"


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
    creatives, token, seen = [], None, set()

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
            break

    return creatives


def extract_copy(creatives, image_dir, workers=None):
    os.makedirs(image_dir, exist_ok=True)

    def resolve(creative):
        try:
            if creative.format in ("image", "video") and creative.preview_link:
                creative.copy = overlay.shopping_copy(
                    creative.preview_link, creative.format == "image"
                )
            elif creative.preview_link:
                creative.copy = overlay.text_copy(creative.preview_link)

            if not creative.copy and creative.media_url:
                path = os.path.join(image_dir, f"{creative.platform_creative_id}.png")
                blob = _download(creative.media_url, path)
                creative.copy = ocr.extract(blob)
                if creative.copy:
                    creative.copy["image_path"] = path

        except Exception as exc:
            creative.copy = {
                "extraction_source": "error",
                "error": f"{type(exc).__name__}: {exc}",
            }

        if not creative.copy:
            creative.copy = {"extraction_source": "error", "error": "no copy recovered"}
        return creative

    with ThreadPoolExecutor(max_workers=workers or settings.WORKERS) as pool:
        list(pool.map(resolve, creatives))

    return creatives
