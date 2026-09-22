# Ad Intelligence Pipeline

Tracks the ads that UK beauty retailers are running across **Google Ads Transparency
Center**, **Google Search** and **Meta (Facebook/Instagram)**, recovers the actual ad
copy, and stores everything in MySQL so it can be queried over time.

---

## ⚠️ Scope — read before running

This is configured for specific retailers and a specific market. It is not a
general-purpose scraper.

| Setting | Value |
|---|---|
| Retailers | LookFantastic, John Lewis, Boots |
| Region | United Kingdom (`GB`) |
| Platforms | `google_ads`, `google_search`, `meta` |
| Tracked brands | Clinique, MAC, Tom Ford, Jo Malone, Bobbi Brown, Estee Lauder, Too Faced |
| Window | last N days, `--days` (default 1) |

TikTok was investigated and **deliberately excluded** — see [Known limitations](#known-limitations).

---

## Setup

### 1. OCR engine (not a pip package)

Google serves most of its ad copy as pixels, so a real OCR engine is required.

```bash
sudo apt install tesseract-ocr
```

macOS: `brew install tesseract` · Windows: <https://github.com/UB-Mannheim/tesseract/wiki>

Verify with `tesseract --version` (expect 5.x).

### 2. Python packages

Requires Python 3.10+ (tested on 3.12).

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 3. MySQL

Must be running and reachable. The database is created for you.

### 4. Credentials

Create `.env` in the project root:

```
SERP_API_KEY=your_serpapi_key
SEARCH_API_KEYS=key1,key2,key3

DB_HOST=localhost
DB_PORT=3306
DB_USER=root
DB_PASSWORD=root
DB_NAME=ocr_scraper
```

`SEARCH_API_KEYS` is comma-separated and rotated automatically to spread credit usage.

### 5. Create the tables

```bash
./venv/bin/python -m adintel init-db
```

---

## Running with Docker

You do **not** need MySQL, Python or tesseract installed — only Docker Desktop.

### Setup — one command

Put your keys in `.env` first:

```
SERP_API_KEY=your_key
SEARCH_API_KEYS=key1,key2,key3
DB_PASSWORD=root
DB_NAME=ocr_scraper
```

Then:

```bash
docker compose up -d
```

That builds the image, starts MySQL, waits for it to be ready, creates all the
tables, and leaves the app running and idle. You only run this once.

### Running commands

```bash
docker compose exec adintel python -m adintel scrape --retailer lookfantastic --platform meta --limit 10
docker compose exec adintel python -m adintel status
docker compose exec adintel python -m adintel ask "which promo codes are running?"
```

Output appears in `./output` on your machine.

### Code changes are live

`adintel/`, `tests/` and `fixtures/` are mounted from your disk into the container.
Edit a file, save, run the command again — the change is already active.

**No rebuild needed for code changes.** Rebuild only when `requirements.txt`
changes:

```bash
docker compose up -d --build
```

### Stopping and starting

```bash
docker compose down     # stop (data is kept)
docker compose up -d    # start again
```

### Ollama stays outside Docker

GPU passthrough into Docker on Windows needs the NVIDIA Container Toolkit and
extra RAM. Install [Ollama for Windows](https://ollama.com/download) instead — it
uses the GPU natively, and the container already reaches it through
`host.docker.internal:11434`.

```bash
ollama pull qwen2.5-coder:7b
```

Ollama is only needed for the `ask` command; everything else works without it.

### Connecting a database client

MySQL is published on **port 3307** (not 3306, to avoid clashing with any local
install):

```
host: localhost   port: 3307   user: root   password: <DB_PASSWORD>
```

---

## Running it (native, no Docker)

```bash
./venv/bin/python -m adintel scrape --retailer lookfantastic --platform all
```

| Flag | Meaning |
|---|---|
| `--retailer` | `lookfantastic`, `johnlewis`, `boots` |
| `--platform` | `google_ads`, `google_search`, `meta`, or `all` |
| `--days` | window size, default 1 |
| `--limit` | stop after N creatives — **use this while testing** |
| `--no-db` | write JSON only, skip MySQL |

Always test with a small limit first — a full day for one retailer is ~2,500 creatives:

```bash
./venv/bin/python -m adintel scrape --retailer lookfantastic --platform meta --limit 10
```

---

## What it does

```
1. FETCH     Pull creatives for the retailer + window from each platform.
                    ↓
2. RECOVER   Get the ad copy, which differs per platform:
               google_ads    → decode the URL blob, else download + OCR the screenshot
               meta          → plain text from the API (no OCR needed)
               google_search → plain text, filtered to the retailer's own domain
                    ↓
3. CLASSIFY  Tag each ad brand / category / generic, match tracked brands,
             and pull out promo codes and discounts.
                    ↓
4. STORE     Write JSON files AND upsert into MySQL (idempotent).
```

### Why two vendors

| Platform | Vendor | Reason |
|---|---|---|
| `google_ads` | SerpApi | Only SerpApi exposes the creative preview link whose blob yields exact text with no OCR |
| `google_search`, `meta` | SearchAPI.io | SerpApi has no Meta engine |

---

## Output

Every run writes JSON **and** rows to MySQL. JSON is organised retailer-first, so
everything about one retailer lives together:

```
output/
├── boots/
│   ├── ads_transparency/
│   │   ├── 2026-09-21_16-05-32.json       all creatives from that run
│   │   ├── filtered/
│   │   │   └── 2026-09-21_16-05-32.json   only the tracked brands
│   │   └── images/
│   │       └── 2026-09-21_16-05-32/       screenshots from that run
│   └── meta_ads/
│       ├── 2026-09-21_16-11-48.json
│       └── filtered/
│           └── 2026-09-21_16-11-48.json
└── johnlewis/
    └── google_search/
        ├── 2026-09-21_16-20-15.json
        └── filtered/
            └── 2026-09-21_16-20-15.json
```

Filenames are `YYYY-MM-DD_HH-MM-SS.json`, so sorting alphabetically sorts by time —
the newest run is always last.

A run and its filtered output **share the same timestamp**, so you can always tell
which filtered file came from which run. `filtered/` sits inside each platform
folder rather than at retailer level, so Google and Meta results never mix.

Images live under `ads_transparency/` because only Google produces them.

| platform flag | folder |
|---|---|
| `google_ads` | `ads_transparency` |
| `google_search` | `google_search` |
| `meta` | `meta_ads` |

### Database

12 tables. Shared core plus per-platform detail tables, so cross-platform
questions stay a single join.

| Table | Holds |
|---|---|
| `retailers`, `brands` | reference data |
| `runs` | one row per platform+retailer execution, with stats and credits used |
| `creatives` | one row per unique ad, deduped on `(platform, platform_creative_id)` |
| `creative_copy` | headline, description, landing URL, how it was extracted |
| `creative_offers` | promo codes and discount percentages |
| `creative_brands` | which tracked brands each ad mentions |
| `creative_sitelinks` | the sub-links under an ad |
| `creative_observations` | **which run saw which ad** — this is what makes change-tracking possible |
| `meta_ad_details`, `google_search_ad_details` | platform-specific fields |

Re-running the same window **updates** rather than duplicates.

### Useful queries

Campaign mix per platform:

```sql
SELECT platform, campaign_type, COUNT(*) FROM creatives GROUP BY 1,2;
```

Live promo codes:

```sql
SELECT o.promo_code, COUNT(*) ads FROM creative_offers o
WHERE o.promo_code IS NOT NULL GROUP BY 1 ORDER BY 2 DESC;
```

Ads new since yesterday:

```sql
SELECT c.platform, cc.headline FROM creatives c
JOIN creative_copy cc ON cc.creative_id = c.id
WHERE c.first_seen_at >= CURDATE();
```

Which retailers advertise a given brand:

```sql
SELECT r.name, b.canonical_name, COUNT(*) FROM creative_brands cb
JOIN creatives c ON c.id = cb.creative_id
JOIN brands b ON b.id = cb.brand_id
JOIN retailers r ON r.id = c.retailer_id
GROUP BY 1,2 ORDER BY 3 DESC;
```

### Checking on things

```bash
./venv/bin/python -m adintel status
```

Shows recent runs (with failures), creatives by retailer/platform/type, how fresh
the data is, and credits consumed per platform.

---

## Asking questions in English

A local Ollama model turns a question into SQL, checks it is read-only, and runs it.

```bash
./venv/bin/python -m adintel ask "which promo codes are running on meta?"
./venv/bin/python -m adintel ask "how many brand campaigns per retailer?" --sql-only
```

Ollama is installed under `~/.local/ollama` (no sudo needed). Start it with:

```bash
./scripts/start_ollama.sh
```

It uses the GPU automatically — CUDA is detected on the RTX 4060 — and falls back
to CPU if VRAM is short. The model is `qwen2.5-coder:7b` (~4.7 GB).
Every generated query is rejected unless it starts with `SELECT`, contains no
write keywords, and is a single statement.

This is **text-to-SQL, not vector RAG** — the data is structured and the questions
are analytical, so letting MySQL aggregate is both cheaper and more accurate.

The prompt carries the schema, the table relationships and four worked examples,
because a local 7B model otherwise over-joins (silently dropping rows) or invents
column names. If a query still fails, the MySQL error is fed back for one retry —
the response reports how many `attempts` were needed. Verify the `sql` field on
anything important; a 7B is good at simple aggregates, weaker on complex joins.

---

## Configuration

| What | Where |
|---|---|
| Retailers, domains, Meta page IDs, keywords | `adintel/config/retailers.py` |
| Tracked brands and category terms | `adintel/config/brands.py` |
| API keys, DB, workers, Ollama model | `adintel/config/settings.py` + `.env` |

### Adding a retailer

```python
"newretailer": Retailer(
    slug="newretailer",
    name="New Retailer",
    domain="newretailer.com",
    meta_page_id="123456789",
    search_keywords=("new retailer beauty",),
),
```

`meta_page_id` must be the retailer's own Facebook page ID. Keyword search will
not find it reliably — Meta matches ad *text*, so other brands saying "available
at X" drown out X itself.

### Adding a brand

```python
"Your Brand": r"\byour\s+brand\b",
```

Patterns run against normalised text (accents stripped, punctuation flattened,
lowercased), so `Estée Lauder` and `M.A.C` match without extra work. Use
character classes like `[il1]` and `[o0]` to absorb OCR misreads.

---

## Tests

```bash
./venv/bin/python tests/test_extraction.py
./venv/bin/python tests/test_insights_safety.py
./venv/bin/python tests/test_ocr.py
```

`test_extraction.py` covers brand matching (including OCR misreads and
false-positive guards), campaign classification, offer parsing, and domain/seller
filtering — all against fixtures, so it costs no API credits.
`test_insights_safety.py` proves the text-to-SQL guard blocks writes, DDL and
stacked statements. `test_ocr.py` runs the real OCR over archived screenshots.

---

## Troubleshooting

**Every Google ad fails with a connection error**

An ad blocker is sinkholing Google's image CDN. The run warns you up front. Check:

```bash
getent hosts tpc.googlesyndication.com
```

`0.0.0.0` means blocked — allowlist it in your DNS/VPN. Note only the OCR path
breaks; overlay-decoded and Meta ads are unaffected.

**`TesseractNotFoundError`** — OCR engine not installed, see Setup step 1.

**`google_search` returns 0 creatives** — normal. Text ads are auction-driven and
often absent, especially on branded queries. Shopping listings are still captured.

**Meta headline is `{{product.name}}`** — should not happen; dynamic ads are
resolved from their cards. If you see it, the ad has no cards.

---

## Known limitations

- **TikTok is excluded, deliberately.** LookFantastic is not a registered TikTok
  advertiser — searched `GB`, worldwide, and by name variants, all zero. Keyword
  search returns only influencer videos mentioning the brand, whose `title` is
  hashtags rather than ad copy. There is nothing to collect.
- **Google never gives the real landing URL**, only the display URL. Meta does.
- **Some Google text is permanently unrecoverable** — Google truncates its own
  previews with `...`, and on some ads a product photo physically covers the words.
- **Boots has no `meta_page_id`.** Its Facebook page would not surface through
  keyword search. Supply the ID to enable Meta for Boots.
- **Google image-format ads usually are not the retailer's** — they are shopping
  ads run by comparison services (Productcaster, Klarna, Aldoor).
- **Credits are finite.** Runs record `credits_used`; always develop with `--limit`.
