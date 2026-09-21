"""Orchestrates one platform + retailer run: fetch, extract, classify, persist."""

import json
from collections import Counter
from dataclasses import asdict
from datetime import datetime

from adintel.classification import campaign_type
from adintel.classification.brands import match as match_brands
from adintel.config import settings
from adintel.config.retailers import get_retailer
from adintel.extraction import offers
from adintel.sources import google_search, google_transparency, meta
from adintel.sources.base import window
from adintel.sources.client import SearchApiClient, SerpApiClient
from adintel.storage import repository

PLATFORMS = ("google_ads", "google_search", "meta")


def _enrich(creatives):
    for creative in creatives:
        copy = creative.copy or {}
        headline = copy.get("headline")
        brands = match_brands(headline) if headline else []
        copy["brands"] = brands
        copy["campaign_type"] = campaign_type.classify(headline, brands)
        copy["offers"] = offers.parse(copy)
        creative.copy = copy
    return creatives


def _serialise(creative):
    record = asdict(creative)
    for key in ("first_shown", "last_shown"):
        if record.get(key):
            record[key] = record[key].isoformat()
    details = record.get("platform_details") or {}
    for key, value in list(details.items()):
        if isinstance(value, datetime):
            details[key] = value.isoformat()
    return record


def _write_json(directory, filename, payload):
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str),
                    encoding="utf-8")
    return path


def _open_run(retailer, platform, run_uid, start_date, end_date, persist):
    if not persist:
        return None, None, None
    connection = repository.connect()
    repository.sync_reference_data(connection, [retailer])
    retailer_pk = repository.retailer_id(connection, retailer.slug)
    run_pk = repository.start_run(
        connection, run_uid, platform, retailer_pk,
        retailer.region, start_date, end_date,
    )
    return connection, retailer_pk, run_pk


def run(platform, retailer_slug, days=1, limit=None, persist=True):
    if platform not in PLATFORMS:
        raise SystemExit(f"Unknown platform '{platform}'. Known: {', '.join(PLATFORMS)}")

    retailer = get_retailer(retailer_slug)
    run_uid = datetime.now().strftime("%Y%m%d_%H%M%S")
    start_date, end_date = window(days)
    credits_used = 0
    warnings = []

    connection, retailer_pk, run_pk = _open_run(
        retailer, platform, run_uid, start_date, end_date, persist
    )

    try:
        return _execute(platform, retailer, run_uid, start_date, end_date, limit,
                        connection, retailer_pk, run_pk, warnings)
    except Exception as exc:
        if connection and run_pk:
            repository.finish_run(connection, run_pk, "failed", 0, credits_used,
                                  {}, None, f"{type(exc).__name__}: {exc}")
        raise
    finally:
        if connection:
            connection.close()


def _execute(platform, retailer, run_uid, start_date, end_date, limit,
             connection, retailer_pk, run_pk, warnings):
    credits_used = 0

    if platform == "google_ads":
        blocked = google_transparency.image_host_blocked()
        if blocked:
            warnings.append(f"image CDN unreachable: {blocked} - OCR will fail")
            print(f"WARNING: {warnings[-1]}")
        client = SerpApiClient()
        creatives = google_transparency.fetch(client, retailer, start_date, end_date, limit)
        image_dir = settings.OUTPUT_DIR / "img" / run_uid
        google_transparency.extract_copy(creatives, image_dir)
        credits_used = client.calls

    elif platform == "meta":
        client = SearchApiClient()
        creatives = meta.fetch(client, retailer, start_date, end_date, limit)
        credits_used = client.calls

    elif platform == "google_search":
        client = SearchApiClient()
        creatives = google_search.fetch(client, retailer, limit=limit)
        credits_used = client.calls

    _enrich(creatives)

    stats = Counter((c.copy or {}).get("extraction_source", "none") for c in creatives)
    types = Counter((c.copy or {}).get("campaign_type", "none") for c in creatives)
    brand_counts = Counter(
        name for c in creatives for name in (c.copy or {}).get("brands", [])
    )

    records = [_serialise(c) for c in creatives]
    payload = {
        "run_uid": run_uid,
        "platform": platform,
        "retailer": retailer.slug,
        "region": retailer.region,
        "window_start": start_date.isoformat(),
        "window_end": end_date.isoformat(),
        "credits_used": credits_used,
        "extraction_stats": dict(stats),
        "campaign_types": dict(types),
        "brand_counts": dict(brand_counts),
        "creative_count": len(records),
        "creatives": records,
    }

    json_path = _write_json(
        settings.OUTPUT_DIR / "transparency_data" / platform,
        f"{retailer.slug}_{run_uid}.json",
        payload,
    )

    matched = [r for r in records if r["copy"].get("brands")]
    _write_json(
        settings.OUTPUT_DIR / "filtered_brands",
        f"{retailer.slug}_{platform}_{run_uid}.json",
        {
            "run_uid": run_uid,
            "platform": platform,
            "retailer": retailer.slug,
            "brand_counts": dict(brand_counts),
            "matched_count": len(matched),
            "creatives": matched,
        },
    )

    saved = 0
    if connection and run_pk:
        saved = repository.save_creatives(
            connection, run_pk, retailer_pk, creatives,
            repository.brand_ids(connection),
        )
        repository.finish_run(
            connection, run_pk, "success", len(creatives),
            credits_used, dict(stats), json_path,
        )

    return {
        "run_uid": run_uid,
        "platform": platform,
        "retailer": retailer.slug,
        "creatives": len(creatives),
        "saved_to_db": saved,
        "credits_used": credits_used,
        "warnings": warnings,
        "extraction": dict(stats),
        "campaign_types": dict(types),
        "brands": dict(brand_counts),
        "json_path": str(json_path),
    }
