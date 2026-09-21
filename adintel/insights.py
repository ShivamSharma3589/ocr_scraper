"""Natural-language questions answered as SQL against the ad database.

Uses a local Ollama model. The schema is small and stable, so the model is given
the full table layout rather than retrieving fragments of it - for structured
analytics that is both cheaper and more accurate than vector retrieval.
"""

import json
import re

import requests

from adintel.config import settings
from adintel.storage import repository

SCHEMA_SUMMARY = """
retailers(id, slug, name, domain, region, meta_page_id)
brands(id, canonical_name, match_pattern, is_active)
runs(id, run_uid, platform, retailer_id, region, window_start, window_end,
     started_at, finished_at, status, creatives_seen, credits_used, stats)
advertisers(id, platform, platform_advertiser_id, name)
creatives(id, platform, platform_creative_id, retailer_id, advertiser_id, format,
          campaign_type, first_shown, last_shown, total_days_shown, details_url,
          media_url, image_path, first_seen_at, last_seen_at)
creative_copy(creative_id, extraction_source, headline, description, display_url,
              landing_url, cta_text, raw_text, is_truncated, extracted_at)
creative_offers(id, creative_id, promo_code, discount_text, discount_pct)
creative_brands(creative_id, brand_id)
creative_sitelinks(id, creative_id, title, description)
creative_observations(id, creative_id, run_id, observed_at)
meta_ad_details(creative_id, page_id, page_name, publisher_platforms, is_active,
                start_date, end_date, caption, link_description, cta_type, currency)
google_search_ad_details(creative_id, keyword, position, block_position)

platform is one of: google_ads, google_search, meta
campaign_type is one of: brand, category, generic
"""

RELATIONSHIPS = """
creative_copy.creative_id   -> creatives.id   (1:1, headline/description live here)
creative_offers.creative_id -> creatives.id   (0:N, promo codes and discounts)
creative_brands.creative_id -> creatives.id   (0:N, join brands on brand_id)
creative_observations       -> creatives.id and runs.id (which run saw which ad)
creatives.retailer_id       -> retailers.id
meta_ad_details.creative_id -> creatives.id   (meta only)

Only join a table you actually need. Joining creative_copy or creative_brands
silently drops creatives that have no copy or no brand.
"""

EXAMPLES = """
Q: how many creatives per platform?
A: SELECT platform, COUNT(*) AS creatives FROM creatives GROUP BY platform LIMIT 50

Q: which promo codes are running and on how many ads?
A: SELECT promo_code, COUNT(DISTINCT creative_id) AS ads FROM creative_offers
   WHERE promo_code IS NOT NULL GROUP BY promo_code ORDER BY ads DESC LIMIT 50

Q: how many brand campaigns does each retailer have?
A: SELECT r.name, COUNT(*) AS campaigns FROM creatives c
   JOIN retailers r ON r.id = c.retailer_id
   WHERE c.campaign_type = 'brand' GROUP BY r.name ORDER BY campaigns DESC LIMIT 50

Q: which brands does lookfantastic advertise?
A: SELECT b.canonical_name, COUNT(*) AS ads FROM creative_brands cb
   JOIN brands b ON b.id = cb.brand_id
   JOIN creatives c ON c.id = cb.creative_id
   JOIN retailers r ON r.id = c.retailer_id
   WHERE r.slug = 'lookfantastic' GROUP BY b.canonical_name ORDER BY ads DESC LIMIT 50
"""

PROMPT = """You are a MySQL expert. Write ONE SELECT query answering the question.

Schema:
{schema}

Relationships:
{relationships}

Worked examples:
{examples}

Rules:
- SELECT only. Never INSERT, UPDATE, DELETE, DROP or ALTER.
- Use only columns that appear in the schema above.
- Prefer the simplest query. Do not join tables you do not need.
- Always end with LIMIT 50 or fewer.
- Return only the SQL. No explanation, no markdown fences.

Question: {question}
SQL:"""

RETRY_PROMPT = """That query failed with this MySQL error:

{error}

Rewrite it as ONE valid SELECT using only columns from the schema above.
Return only the corrected SQL.

Question: {question}
SQL:"""

FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|truncate|create|grant|replace)\b", re.I
)


class OllamaUnavailable(RuntimeError):
    pass


def check_ollama(url=None, model=None):
    """Return a human-readable problem, or None when ready to answer questions."""
    base = url or settings.OLLAMA_URL
    wanted = model or settings.OLLAMA_MODEL
    try:
        response = requests.get(f"{base}/api/tags", timeout=10)
        response.raise_for_status()
    except Exception:
        return (f"cannot reach Ollama at {base} - start it with "
                "./scripts/start_ollama.sh")

    names = [m.get("name", "") for m in response.json().get("models", [])]
    if not any(n == wanted or n.startswith(wanted.split(":")[0]) for n in names):
        installed = ", ".join(names) or "none"
        return (f"model '{wanted}' is not installed (have: {installed}) - "
                f"run: ollama pull {wanted}")
    return None


def generate_sql(question, model=None, url=None, prompt=None):
    problem = check_ollama(url, model)
    if problem:
        raise OllamaUnavailable(problem)

    response = requests.post(
        f"{url or settings.OLLAMA_URL}/api/generate",
        json={
            "model": model or settings.OLLAMA_MODEL,
            "prompt": prompt or PROMPT.format(
                schema=SCHEMA_SUMMARY, relationships=RELATIONSHIPS,
                examples=EXAMPLES, question=question,
            ),
            "stream": False,
            "options": {"temperature": 0},
        },
        timeout=300,
    )
    response.raise_for_status()
    sql = response.json().get("response", "").strip()
    sql = re.sub(r"^```(?:sql)?|```$", "", sql, flags=re.M).strip()
    return sql.rstrip(";").strip()


def is_safe(sql):
    if not sql.lower().lstrip().startswith("select"):
        return False, "query must start with SELECT"
    if FORBIDDEN.search(sql):
        return False, "query contains a forbidden keyword"
    if ";" in sql:
        return False, "multiple statements are not allowed"
    return True, None


def run_sql(sql, limit=50):
    connection = repository.connect()
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"EXPLAIN {sql}")
            cursor.execute(sql)
            return cursor.fetchmany(limit)
    finally:
        connection.close()


def ask(question, model=None, attempts=2):
    """Generate SQL, run it, and feed any MySQL error back for one retry."""
    sql = error = None

    for attempt in range(attempts):
        prompt = None
        if attempt and error:
            prompt = (
                PROMPT.format(schema=SCHEMA_SUMMARY, relationships=RELATIONSHIPS,
                              examples=EXAMPLES, question=question)
                + "\n" + RETRY_PROMPT.format(error=error, question=question)
            )

        try:
            sql = generate_sql(question, model=model, prompt=prompt)
        except OllamaUnavailable as exc:
            return {"question": question, "sql": None, "error": str(exc), "rows": []}
        except Exception as exc:
            return {"question": question, "sql": None,
                    "error": f"{type(exc).__name__}: {exc}", "rows": []}

        safe, reason = is_safe(sql)
        if not safe:
            return {"question": question, "sql": sql, "error": reason, "rows": []}

        try:
            rows = run_sql(sql)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            continue

        return {"question": question, "sql": sql, "attempts": attempt + 1,
                "row_count": len(rows),
                "rows": json.loads(json.dumps(rows, default=str))}

    return {"question": question, "sql": sql, "attempts": attempts,
            "error": error, "rows": []}
