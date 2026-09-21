"""Meta Ad Library via SearchAPI. Returns ad copy as plain text - no OCR."""

import re
from datetime import date

from adintel.sources.base import Creative, to_datetime

PLATFORM = "meta"

TEMPLATE_RE = re.compile(r"\{\{.*?\}\}")


def _text(value):
    if isinstance(value, dict):
        value = value.get("text") or value.get("markup")
    return value


def _is_template(value):
    return bool(value) and bool(TEMPLATE_RE.search(str(value)))


def _copy_from_snapshot(snapshot):
    """Dynamic (DCO) ads store '{{product.name}}' placeholders in the snapshot;
    their real copy lives in the first card."""
    headline = _text(snapshot.get("title"))
    description = _text(snapshot.get("body"))
    caption = _text(snapshot.get("caption"))
    landing_url = snapshot.get("link_url")
    cta = snapshot.get("cta_text")

    cards = snapshot.get("cards") or []
    if cards and (_is_template(headline) or _is_template(description)):
        card = cards[0]
        if _is_template(headline):
            headline = _text(card.get("title")) or headline
        if _is_template(description):
            description = _text(card.get("body")) or description
        landing_url = card.get("link_url") or landing_url
        caption = caption or _text(card.get("caption"))
        cta = cta or card.get("cta_text")

    sitelinks = [
        {"title": _text(c.get("title")), "description": _text(c.get("body"))}
        for c in cards[1:6]
        if _text(c.get("title")) and not _is_template(c.get("title"))
    ]

    return {
        "extraction_source": "api",
        "headline": headline,
        "description": description,
        "display_url": caption,
        "landing_url": landing_url,
        "cta_text": cta,
        "sitelinks": sitelinks,
        "is_truncated": False,
        "is_dynamic": bool(cards) and snapshot.get("display_format") == "DCO",
    }


def fetch(client, retailer, start_date=None, end_date=None, limit=None, max_pages=5):
    if not retailer.meta_page_id:
        raise ValueError(f"{retailer.slug} has no meta_page_id configured")

    creatives, token, pages = [], None, 0

    while pages < max_pages:
        params = {
            "engine": "meta_ad_library",
            "page_id": retailer.meta_page_id,
            "country": retailer.region,
            "active_status": "active",
            "sort_by": "most_recent",
        }
        if start_date:
            params["start_date"] = start_date.strftime("%Y-%m-%d")
        if end_date:
            params["end_date"] = min(end_date, date.today()).strftime("%Y-%m-%d")
        if token:
            params["next_page_token"] = token

        data = client.get(params)
        ads = data.get("ads") or []
        if not ads:
            break

        for ad in ads:
            snapshot = ad.get("snapshot") or {}
            creatives.append(Creative(
                platform=PLATFORM,
                platform_creative_id=str(ad.get("ad_archive_id")),
                format=snapshot.get("display_format"),
                advertiser_id=str(ad.get("page_id")),
                advertiser_name=ad.get("page_name"),
                first_shown=to_datetime(ad.get("start_date")),
                last_shown=to_datetime(ad.get("end_date")),
                copy=_copy_from_snapshot(snapshot),
                platform_details={
                    "page_id": str(ad.get("page_id") or ""),
                    "page_name": ad.get("page_name"),
                    "publisher_platforms": ad.get("publisher_platform"),
                    "is_active": ad.get("is_active"),
                    "start_date": to_datetime(ad.get("start_date")),
                    "end_date": to_datetime(ad.get("end_date")),
                    "caption": (snapshot.get("caption") or "")[:512] or None,
                    "link_description": snapshot.get("link_description"),
                    "cta_type": snapshot.get("cta_type"),
                    "currency": ad.get("currency"),
                },
                raw=ad,
            ))
            if limit and len(creatives) >= limit:
                return creatives

        pages += 1
        token = (data.get("pagination") or {}).get("next_page_token")
        if not token:
            break

    return creatives
