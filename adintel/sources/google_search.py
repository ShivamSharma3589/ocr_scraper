"""Live Google SERP ads via SearchAPI, filtered to the retailer's own domain.

Text ads are auction-driven, so a query can legitimately return none. Shopping
listings arrive in the same paid response and are captured when the seller
matches the retailer.
"""

import hashlib
from urllib.parse import urlparse

from adintel.sources.base import Creative

PLATFORM = "google_search"


def _domain_of(*values):
    for value in values:
        if not value:
            continue
        text = str(value).strip().lower()
        if text.startswith("http"):
            text = urlparse(text).netloc
        text = text.split("/")[0].removeprefix("www.")
        if "." in text:
            return text
    return ""


def _matches_domain(ad, domain):
    target = domain.removeprefix("www.").lower()
    found = _domain_of(ad.get("domain"), ad.get("displayed_link"), ad.get("link"))
    return bool(found) and (found == target or found.endswith("." + target))


def _usable_url(url):
    if not url or str(url).startswith("data:"):
        return None
    return str(url)[:1024]


def _matches_seller(item, retailer):
    seller = (item.get("seller") or "").strip().lower()
    if not seller:
        return False
    name = retailer.name.lower().replace(" ", "")
    return name in seller.replace(" ", "") or retailer.domain.split(".")[0] in seller


def _identity(prefix, keyword, *parts):
    digest = hashlib.md5("|".join(str(p or "") for p in parts).encode()).hexdigest()[:10]
    return f"{prefix}:{keyword}:{digest}"


def _text_ad(ad, keyword, retailer):
    return Creative(
        platform=PLATFORM,
        platform_creative_id=_identity(
            "text", keyword, _domain_of(ad.get("link")), ad.get("title")
        ),
        format="text",
        advertiser_name=ad.get("source") or retailer.name,
        details_url=ad.get("link"),
        copy={
            "extraction_source": "api",
            "headline": ad.get("title"),
            "description": ad.get("snippet"),
            "display_url": ad.get("displayed_link"),
            "landing_url": ad.get("link"),
            "sitelinks": [
                {"title": s.get("title"), "description": s.get("snippet")}
                for s in (ad.get("sitelinks") or [])
            ],
            "is_truncated": False,
        },
        platform_details={
            "keyword": keyword,
            "position": ad.get("position"),
            "block_position": ad.get("block_position"),
        },
        raw=ad,
    )


def _shopping_ad(item, keyword, retailer):
    return Creative(
        platform=PLATFORM,
        platform_creative_id=_identity(
            "shop", keyword, item.get("product_id"), item.get("title")
        ),
        format="shopping",
        advertiser_name=item.get("seller") or retailer.name,
        details_url=item.get("link"),
        media_url=_usable_url(item.get("thumbnail")),
        copy={
            "extraction_source": "api",
            "headline": item.get("title"),
            "description": item.get("price"),
            "display_url": item.get("seller"),
            "landing_url": item.get("link"),
            "sitelinks": [],
            "is_truncated": False,
        },
        platform_details={
            "keyword": keyword,
            "position": item.get("position"),
            "block_position": "shopping",
        },
        raw=item,
    )


def parse(data, keyword, retailer):
    creatives = []
    for ad in (data.get("ads") or []):
        if _matches_domain(ad, retailer.domain):
            creatives.append(_text_ad(ad, keyword, retailer))
    for item in (data.get("inline_shopping") or []):
        if _matches_seller(item, retailer):
            creatives.append(_shopping_ad(item, keyword, retailer))
    return creatives


def fetch(client, retailer, keywords=None, limit=None):
    keywords = keywords or retailer.search_keywords
    creatives, seen = [], set()

    for keyword in keywords:
        data = client.get({
            "engine": "google",
            "q": keyword,
            "gl": retailer.region.lower(),
            "hl": "en",
            "location": "United Kingdom" if retailer.region == "GB" else None,
        })

        for creative in parse(data, keyword, retailer):
            if creative.platform_creative_id in seen:
                continue
            seen.add(creative.platform_creative_id)
            creatives.append(creative)
            if limit and len(creatives) >= limit:
                return creatives

    return creatives
