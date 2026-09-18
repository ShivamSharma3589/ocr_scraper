# LookFantastic Ad Campaign Scraper

Pulls the Google ads that **LookFantastic** is currently running in the **UK**, and
recovers the actual ad text — headline, description, discount and promo code —
which the API does not give you directly.

---

## ⚠️ Read this first: what this tool is and is not

This is **not** a general-purpose ad scraper. It is hardcoded for one brand, one
country and one date. Running it as-is gives you LookFantastic UK ads for
17 September 2026 — nothing else.

| Setting | Current value | Meaning |
|---|---|---|
| Advertiser | `lookfantastic.com` | Only this domain's ads |
| Country | `2826` | United Kingdom only |
| Date | `20260917` → `20260918` | **One single day**, not "today" |
| Ad formats | all | text, image and video |
| Platforms | all | Search, Display, YouTube, Shopping |
| Brand filter | 7 brands | Clinique, MAC, Tom Ford, Jo Malone, Bobbi Brown, Estee Lauder, Too Faced |

**The date does not update itself.** It is a fixed value in the code. If you run
this next month without editing it, you will still get 17 September 2026 data.
See [Changing what it scrapes](#changing-what-it-scrapes).

---

## Setup

### 1. Install the OCR engine (this is not a pip package)

Most of the ad text only exists as pixels inside a screenshot, so the tool needs
a real OCR engine. `pip install` **cannot** provide this — install it separately:

```bash
sudo apt install tesseract-ocr
```

macOS:

```bash
brew install tesseract
```

Windows: download the installer from
<https://github.com/UB-Mannheim/tesseract/wiki>

Check it worked:

```bash
tesseract --version
```

You should see `tesseract 5.x`. If you skip this step, everything installs fine
and then every ad fails at runtime.

### 2. Install the Python packages

Requires **Python 3.9 or newer** (tested on 3.12).

```bash
python3 -m venv venv
./venv/bin/pip install -r requirements.txt
```

### 3. Add your SerpApi key

Create a file called `.env` in the project folder:

```
SERP_API_KEY=your_key_here
```

Get a key at <https://serpapi.com>. Each run costs roughly **1 credit per 100 ads**.

> **Never commit `.env` to git.** It contains a live billable key.

---

## Running it

```bash
./venv/bin/python extract.py
```

That's the whole command. A full day is around **2,500 ads** and takes roughly
**8–9 minutes**.

### Try a small run first

Before committing to a full run, do 10 ads to check your setup works:

```bash
./venv/bin/python -c "import extract; extract.LIMIT = 10; extract.main()"
```

This finishes in seconds and produces the same output structure.

---

## What the script actually does

Google's Ads Transparency Center tells you an ad *exists*, but not what it
*says* — no headline, no description, no offer. This tool recovers that text.

```
1. FETCH      Ask SerpApi for every LookFantastic ad in the date window.
              Pages through 100 at a time until there are none left.
                     ↓
2. DOWNLOAD   Each ad is a screenshot of how it looked in Google search.
              Downloads them into this run's image folder.
                     ↓
3. READ       Recover the text two ways:
                • Some ads hide their exact text in the URL  → decoded, perfect
                • The rest are pictures only                 → OCR'd
                     ↓
4. EXTRACT    Pull out promo codes (FLASH22) and discounts (20% Off),
              and group ads that share a headline into campaigns.
                     ↓
5. FILTER     Save ads for your 7 tracked brands into a separate file.
```

### How the text is recovered

Headlines are rendered in blue and descriptions in grey, so the tool reads the
**pixel colour** of each word to tell them apart. Sitelinks (the extra links
below an ad) are blue too, so only the *first* run of blue lines is treated as
the headline.

---

## Understanding the output

Every run creates three things, all stamped with the same timestamp so you can
tell which files belong together:

```
output/
├── img/20260918_073217/            ← the ad screenshots it downloaded
├── transparency_data/20260918_073217.json   ← every ad + its extracted text
└── filtered_brands/20260918_073217.json     ← only your 7 tracked brands
```

### What you see on screen

```
overlay=1  ocr=9  shopping=0  video=0  error=0
deduped:   10 creatives -> 10 campaigns
filtered:  output/filtered_brands/20260918_073217.json  (1 matched)
  brands:  MAC=1
```

| Word | Meaning |
|---|---|
| `overlay` | Text read perfectly from the URL — no OCR needed |
| `ocr` | Text read from the picture |
| `shopping` / `video` | Ads that contain no text at all (see Limitations) |
| `error` | Failed — usually a network problem |
| `campaigns` | Ads grouped together by identical headline |

### Inside the JSON

Each ad gets an `ocr_result` block holding everything that was recovered:

```json
{
  "ad_creative_id": "CR00399539968365559809",
  "first_shown": 1743597722,
  "last_shown": 1789669595,
  "ocr_result": {
    "source": "ocr",
    "headline": "Essie At LOOKFANTASTIC - Declining Discounts Now On",
    "description": "Hurry! 30% Off & Declining 1% Every 2 Hours | Use Code: QUICK...",
    "display_url": "www.lookfantastic.com/",
    "sitelinks": [
      { "title": "Varnish", "description": "Buy Essie Varnish from £10.95..." }
    ],
    "offer": {
      "promo_codes": ["QUICK"],
      "discounts": ["30% Off"]
    }
  }
}
```

The file also has a `campaigns` list at the top — the same ads grouped by
headline, sorted by how many creatives share it. **Start there**, it is far
easier to read than the raw ad list.

### Quick ways to look at it

Top 20 campaigns:

```bash
./venv/bin/python -c "import json,glob; d=json.load(open(sorted(glob.glob('output/transparency_data/*.json'))[-1])); [print(c['creative_count'], c['headline']) for c in d['campaigns'][:20]]"
```

Which brands were found:

```bash
./venv/bin/python -c "import json,glob; d=json.load(open(sorted(glob.glob('output/filtered_brands/*.json'))[-1])); print(d['per_brand_counts'])"
```

---

## Changing what it scrapes

All of it lives at the top of `extract.py`.

### A different date

```python
START_DATE = "20260918"   # the day you want
END_DATE   = "20260919"   # that day + 1  (end is exclusive)
```

For a 30-day window, set `START_DATE` 30 days earlier and leave `END_DATE` as
tomorrow.

### A different brand or country

```python
LIST_PARAMS = {
    "text":   "boots.com",   # any advertiser domain
    "region": "2826",        # 2826 = UK, 2724 = Spain, 2300 = Greece, 2840 = US
    ...
}
```

### Different tracked brands

```python
BRANDS = {
    "Clinique": r"\bcl[il1]n[il1][qg]ue\b",
    "Your Brand": r"\byour\s+brand\b",
}
```

Patterns look odd on purpose. OCR misreads letters — `i` as `l` or `1`, `o` as
`0`, `q` as `g` — so `[il1]` means "any of these". Accents and punctuation are
already handled automatically, so `Estée Lauder`, `Estee Lauder` and `M.A.C` all
match without extra work. Set `BRANDS = {}` to skip filtering.

### Speed

```python
WORKERS = 8   # raise for a faster run, lower if the network struggles
```

---

## Troubleshooting

**Every ad fails with "network connection failed"**

Your DNS is probably blocking Google's ad server. Ad blockers, Pi-hole and some
VPNs sinkhole it. Check:

```bash
getent hosts tpc.googlesyndication.com
```

If it returns `0.0.0.0`, that's the problem — allowlist
`tpc.googlesyndication.com` in whatever is blocking it. The script warns you
about this before it starts.

**`TesseractNotFoundError`**

The OCR engine isn't installed. Go back to Setup step 1.

**Ads come back but headlines are empty**

Normal for `shopping` and `video` ads — they genuinely contain no text.

---

## Known limitations

These are real constraints, not bugs to fix:

- **Some text is unreadable, permanently.** Google truncates its own ad
  previews with `...`, and on some ads a product photo physically covers the
  words. That text does not exist in any retrievable form.
- **Video ads have no text at all.** Nothing to extract.
- **Image ads are usually not LookFantastic's.** They're shopping ads run by
  price-comparison resellers (Productcaster, Klarna, Aldoor).
- **Grouping by headline is weak.** Google auto-generates a near-unique headline
  per ad, so ~2,500 ads collapse to only ~2,100 "campaigns". Grouping by promo
  code instead (there are only ~30) gives a far more useful picture.
- **One country, one day per run.** LookFantastic also advertises in Greece and
  Spain; those need separate runs with a different `region`.
- **The `ad_details` API is useless here.** It was tested against every ad and
  returns no ad copy whatsoever. Don't spend credits on it.

---

## Project files

| File | Purpose |
|---|---|
| `extract.py` | The whole pipeline. This is the only thing you run. |
| `config.py` | Reads your API key from `.env` |
| `requirements.txt` | Python packages (**plus** the tesseract note) |
| `.env` | Your SerpApi key — never commit this |
| `output/` | Everything the runs produce |
