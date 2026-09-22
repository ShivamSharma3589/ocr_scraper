"""MySQL persistence. Idempotent: re-running a window updates rather than duplicates."""

import json
from datetime import datetime
from pathlib import Path

import pymysql

from adintel.config import settings
from adintel.config.brands import BRANDS

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect():
    return pymysql.connect(
        host=settings.DB["host"],
        port=settings.DB["port"],
        user=settings.DB["user"],
        password=settings.DB["password"],
        database=settings.DB["database"],
        charset="utf8mb4",
        autocommit=False,
        cursorclass=pymysql.cursors.DictCursor,
    )


def ensure_database():
    connection = pymysql.connect(
        host=settings.DB["host"], port=settings.DB["port"],
        user=settings.DB["user"], password=settings.DB["password"],
        charset="utf8mb4", autocommit=True,
    )
    with connection.cursor() as cursor:
        cursor.execute(
            f"CREATE DATABASE IF NOT EXISTS `{settings.DB['database']}` "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
    connection.close()


def apply_schema():
    ensure_database()
    statements = [s.strip() for s in SCHEMA_PATH.read_text().split(";") if s.strip()]
    connection = connect()
    try:
        with connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        connection.commit()
    finally:
        connection.close()


def sync_reference_data(connection, retailers):
    with connection.cursor() as cursor:
        for retailer in retailers:
            cursor.execute(
                """INSERT INTO retailers (slug, name, domain, region, meta_page_id)
                   VALUES (%s, %s, %s, %s, %s)
                   ON DUPLICATE KEY UPDATE
                     name=VALUES(name), domain=VALUES(domain),
                     region=VALUES(region), meta_page_id=VALUES(meta_page_id)""",
                (retailer.slug, retailer.name, retailer.domain,
                 retailer.region, retailer.meta_page_id),
            )
        for name, pattern in BRANDS.items():
            cursor.execute(
                """INSERT INTO brands (canonical_name, match_pattern)
                   VALUES (%s, %s)
                   ON DUPLICATE KEY UPDATE match_pattern=VALUES(match_pattern)""",
                (name, pattern),
            )
    connection.commit()


def _scalar(cursor, sql, params):
    cursor.execute(sql, params)
    row = cursor.fetchone()
    return list(row.values())[0] if row else None


def retailer_id(connection, slug):
    with connection.cursor() as cursor:
        return _scalar(cursor, "SELECT id FROM retailers WHERE slug=%s", (slug,))


def brand_ids(connection):
    with connection.cursor() as cursor:
        cursor.execute("SELECT id, canonical_name FROM brands")
        return {row["canonical_name"]: row["id"] for row in cursor.fetchall()}


def start_run(connection, run_uid, platform, retailer_pk, region, window_start, window_end):
    with connection.cursor() as cursor:
        cursor.execute(
            """INSERT INTO runs
                 (run_uid, platform, retailer_id, region, window_start, window_end,
                  started_at, status)
               VALUES (%s, %s, %s, %s, %s, %s, %s, 'running')
               ON DUPLICATE KEY UPDATE started_at=VALUES(started_at), status='running'""",
            (run_uid, platform, retailer_pk, region, window_start, window_end,
             datetime.now()),
        )
        connection.commit()
        return _scalar(
            cursor,
            "SELECT id FROM runs WHERE run_uid=%s AND platform=%s AND retailer_id=%s",
            (run_uid, platform, retailer_pk),
        )


def finish_run(connection, run_pk, status, creatives_seen, credits_used, stats, json_path, error=None):
    with connection.cursor() as cursor:
        cursor.execute(
            """UPDATE runs SET finished_at=%s, status=%s, creatives_seen=%s,
                   credits_used=%s, stats=%s, json_path=%s, error_message=%s
               WHERE id=%s""",
            (datetime.now(), status, creatives_seen, credits_used,
             json.dumps(stats), str(json_path) if json_path else None, error, run_pk),
        )
    connection.commit()


def _advertiser_pk(cursor, platform, advertiser_id, name):
    if not advertiser_id:
        return None
    cursor.execute(
        """INSERT INTO advertisers (platform, platform_advertiser_id, name)
           VALUES (%s, %s, %s)
           ON DUPLICATE KEY UPDATE name=COALESCE(VALUES(name), name)""",
        (platform, advertiser_id, name),
    )
    return _scalar(
        cursor,
        "SELECT id FROM advertisers WHERE platform=%s AND platform_advertiser_id=%s",
        (platform, advertiser_id),
    )


def save_creatives(connection, run_pk, retailer_pk, creatives, brand_lookup):
    now = datetime.now()
    saved = 0

    with connection.cursor() as cursor:
        for creative in creatives:
            copy = creative.copy or {}
            advertiser_pk = _advertiser_pk(
                cursor, creative.platform, creative.advertiser_id, creative.advertiser_name
            )

            cursor.execute(
                """INSERT INTO creatives
                     (platform, platform_creative_id, retailer_id, advertiser_id, format,
                      campaign_type, first_shown, last_shown, total_days_shown,
                      details_url, media_url, image_path, first_seen_at, last_seen_at)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                     last_shown=VALUES(last_shown),
                     total_days_shown=VALUES(total_days_shown),
                     campaign_type=VALUES(campaign_type),
                     image_path=COALESCE(VALUES(image_path), image_path),
                     last_seen_at=VALUES(last_seen_at)""",
                (creative.platform, creative.platform_creative_id, retailer_pk,
                 advertiser_pk, creative.format, copy.get("campaign_type"),
                 creative.first_shown, creative.last_shown, creative.total_days_shown,
                 (creative.details_url or "")[:1024] or None,
                 (str(creative.media_url)[:1024] if creative.media_url else None),
                 copy.get("image_path"), now, now),
            )

            creative_pk = _scalar(
                cursor,
                "SELECT id FROM creatives WHERE platform=%s AND platform_creative_id=%s",
                (creative.platform, creative.platform_creative_id),
            )
            if not creative_pk:
                continue
            saved += 1

            cursor.execute(
                """INSERT INTO creative_observations (creative_id, run_id, observed_at)
                   VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE observed_at=VALUES(observed_at)""",
                (creative_pk, run_pk, now),
            )

            if copy.get("headline") or copy.get("description"):
                cursor.execute(
                    """INSERT INTO creative_copy
                         (creative_id, extraction_source, headline, description,
                          display_url, landing_url, cta_text, raw_text, is_truncated,
                          extracted_at)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON DUPLICATE KEY UPDATE
                         extraction_source=VALUES(extraction_source),
                         headline=VALUES(headline), description=VALUES(description),
                         display_url=VALUES(display_url), landing_url=VALUES(landing_url),
                         cta_text=VALUES(cta_text), raw_text=VALUES(raw_text),
                         is_truncated=VALUES(is_truncated), extracted_at=VALUES(extracted_at)""",
                    (creative_pk, copy.get("extraction_source", "unknown"),
                     copy.get("headline"), copy.get("description"),
                     (copy.get("display_url") or "")[:512] or None,
                     copy.get("landing_url"), (copy.get("cta_text") or "")[:128] or None,
                     copy.get("raw_text"), bool(copy.get("is_truncated")), now),
                )

            offers = copy.get("offers") or []
            if offers:
                cursor.execute("DELETE FROM creative_offers WHERE creative_id=%s", (creative_pk,))
                for offer in offers:
                    cursor.execute(
                        """INSERT IGNORE INTO creative_offers
                             (creative_id, promo_code, discount_text, discount_pct)
                           VALUES (%s,%s,%s,%s)""",
                        (creative_pk, offer.get("promo_code"),
                         offer.get("discount_text"), offer.get("discount_pct")),
                    )

            for name in copy.get("brands") or []:
                if name in brand_lookup:
                    cursor.execute(
                        "INSERT IGNORE INTO creative_brands (creative_id, brand_id) VALUES (%s,%s)",
                        (creative_pk, brand_lookup[name]),
                    )

            cursor.execute("DELETE FROM creative_sitelinks WHERE creative_id=%s", (creative_pk,))
            for sitelink in copy.get("sitelinks") or []:
                if sitelink.get("title"):
                    cursor.execute(
                        """INSERT INTO creative_sitelinks (creative_id, title, description)
                           VALUES (%s,%s,%s)""",
                        (creative_pk, sitelink["title"][:255], sitelink.get("description")),
                    )

            _save_platform_details(cursor, creative, creative_pk)

    connection.commit()
    return saved


def _save_platform_details(cursor, creative, creative_pk):
    details = creative.platform_details
    if not details:
        return

    if creative.platform == "meta":
        cursor.execute(
            """INSERT INTO meta_ad_details
                 (creative_id, page_id, page_name, publisher_platforms, is_active,
                  start_date, end_date, caption, link_description, cta_type, currency)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                 is_active=VALUES(is_active), end_date=VALUES(end_date),
                 publisher_platforms=VALUES(publisher_platforms)""",
            (creative_pk, details.get("page_id"), details.get("page_name"),
             json.dumps(details.get("publisher_platforms")), details.get("is_active"),
             details.get("start_date"), details.get("end_date"), details.get("caption"),
             details.get("link_description"), details.get("cta_type"), details.get("currency")),
        )

    elif creative.platform == "google_search":
        cursor.execute(
            """INSERT INTO google_search_ad_details
                 (creative_id, keyword, position, block_position)
               VALUES (%s,%s,%s,%s)
               ON DUPLICATE KEY UPDATE
                 position=VALUES(position), block_position=VALUES(block_position)""",
            (creative_pk, details.get("keyword"), details.get("position"),
             details.get("block_position")),
        )
