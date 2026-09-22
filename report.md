# Competitive Ad Intelligence — POC Findings

**Prepared:** 22 September 2026
**Scope:** UK · LookFantastic, John Lewis, Boots
**Tracked brands:** Clinique, MAC, Tom Ford, Jo Malone, Bobbi Brown, Estée Lauder, Too Faced
**Window:** 15–22 September 2026 (7 days)

---

## 1. Headline finding

**LookFantastic is the only retailer of the three actively discounting your brand portfolio.**

| | Google creatives | Meta creatives | ads naming your brands | live promo codes |
|---|---|---|---|---|
| **LookFantastic** | **7,110** | 150 | **903** | **28** |
| John Lewis | 1,144 | 99 | 3 | 0 |
| Boots | 294 | 150 | **0** | 2 *(own No7 / baby)* |

John Lewis and Boots both advertise beauty, but push own-label and third-party
lines. Neither runs a single promo code against your portfolio.

**Practical implication:** daily monitoring only needs to cover LookFantastic.
The other two justify a weekly or monthly check.

---

## 2. What LookFantastic is doing

### Discount depth — the number to price against

| discount | ads |
|---|---|
| 20% off | **1,938** |
| 25% off | 1,084 |
| 30% off | 760 |
| 22% off | 580 |
| 40% off | 326 |
| 50% off | 60 |

Their standard lever is **20–25% off**. Anything at 40–50% is a thin tail —
386 ads out of 7,110, roughly 5%.

### Promo codes in market

```
FLASH    1,006 ads        TREAT     533
SAVE       650            EXTRA10   183
FLASH22    572            FLASH25   121
EXTRA      547            SAVE5      72
```

28 distinct codes. `FLASH` alone carries 300× the ad volume of their smallest
code — that concentration is a spend signal, not just an offer list.

### Your brands, by pressure

| brand | ads |
|---|---|
| Clinique | 284 |
| Estée Lauder | 203 |
| MAC | 164 |
| Tom Ford | 128 |
| Bobbi Brown | 52 |
| Too Faced | 38 |
| Jo Malone | 34 |

### Tactics, not just offers

Real headlines pulled from the data:

```
"Shop Sol De Janeiro On LF - 25% Off Selected & Declining"
"Essie At LOOKFANTASTIC - Declining Discounts Now On"
   └─ body: "Hurry! 30% Off & Declining 1% Every 2 Hours | Use Code: QUICK"
"The Ordinary At LOOKFANTASTIC - Hurry, Best Sellers Sell Out"
```

A declining-discount mechanic that drops 1% every two hours is a deliberate
urgency play. An offer table would record this as "30% off" and lose the tactic.

---

## 3. The critical limitation — read this before presenting

**Google Ads Transparency caught only 1 of the 4 promo codes live on
LookFantastic's own website.**

| | codes found |
|---|---|
| Website scrape (ground truth) | `EXTRA`, `LFTAKE25`, `LFUNI12`, `MOON25` |
| Google Ads Transparency | 28 codes — but only `EXTRA` overlaps |

Google **missed 3 of 4 live codes**. The website scrape missed 24 of Google's.

### Why they disagree

They answer different questions:

- **Website** → what is redeemable at checkout right now
- **Google Ads** → what they are paying to advertise

A retailer does not advertise every offer — media costs money. Codes like
`LFUNI12` (student) and `MOON25` are distributed through other channels and
never appear in paid search. Conversely, app-exclusive codes (`APP25`,
`APPFLASH`) appear in ads but never on the public site.

**Neither source is complete. Presenting either alone overstates certainty.**

---

## 4. Source-by-source assessment

| | Website scrape | Google Ads Transparency | Meta Ad Library |
|---|---|---|---|
| **legally usable** | ❌ compliance risk | ✅ vendor-licensed | ✅ vendor-licensed |
| live promo codes | ✅ exact, all 4 | ⚠️ 1 of 4 | ✗ 1 code only |
| offer terms & conditions | ✅ | ✗ | ✗ |
| start / end dates | ✗ snapshot | partial | ✅ |
| landing URL | ✅ | ✗ display URL only | ✅ |
| spend weighting | ✗ | ✅ **unique** | partial |
| campaign lifespan | ✗ | ✅ up to 1,792 days observed | ✅ |
| competitor coverage | risky | ✅ any retailer | ✅ any retailer |
| accuracy | exact | ~94% (OCR) | 100% (API text) |

### Meta specifically

Meta is **product-led, not offer-led**. Across 150 LookFantastic ads: one promo
code, 16 discount mentions, and only Estée Lauder of your seven brands appeared.

Its unique value is the real landing URL, showing where paid social spend goes:

```
16  /c/brands/moroccanoil/
16  /c/ace-your-base/
11  /c/brands/estee-lauder/advanced-night-repair
10  /p/estee-lauder-glimmer-eau-de-parfum
```

**Recommendation:** run Meta weekly at ~5 credits for product-push intelligence.
Do not expect discount data from it.

---

## 5. Data quality

| retailer · source | creatives | text recovered | notes |
|---|---|---|---|
| LookFantastic · Google | 7,110 | 6,727 (94%) | 42 genuine errors |
| John Lewis · Google | 1,144 | 532 of 638 text-bearing (83%) | 189 carry no ad copy at all |
| Boots · Google | 294 | 78 | mostly shopping listings |
| all · Meta | 399 | 100% | API returns plain text |

**Known, unfixable gaps:**

- Google truncates its own ad previews with `...`
- On some creatives a product photo physically covers the headline
- Video and shopping creatives contain no ad copy by design
- ~0.2% of promo codes are OCR truncations (`FLA`, `TRE`) — filterable

---

## 6. Routes considered and rejected

**Direct website scraping** — best data quality, but the compliance exposure was
judged unacceptable. Correctly abandoned.

**Awin affiliate network** — retailers publish offers there deliberately, with
terms, end dates and exclusivity flags. Nothing in Awin's UK publisher terms
prohibits this use. Blocked in practice: approval requires an established
promotional website, and promo codes stay hidden until each programme approves
you individually. Revisit if a publisher site is ever stood up.

**`ad_details` endpoint** — returns `title`, `snippet` and `displayed_link`, but
**only for creatives that already expose their text**, which the pipeline
decodes for free. Tested on 4 OCR-dependent creatives: 0 returned text. Using it
instead of OCR would have cost 7,110 credits for ~500 results rather than 72
credits for 6,727.

**Google live SERP ads** — tested twice, returned zero text ads. Paid search
results are auction-dependent, so coverage is unpredictable. Parked.

---

## 7. Recommendation

**Run it. But scope the claim honestly.**

This tells your client **where a competitor is spending, how deeply they
discount, against which brands, and with what tactics** — legally, across any
retailer, with history. That is a defensible product.

It does **not** give a complete list of live promo codes, and should never be
presented as one.

**Suggested cadence**

| | frequency | credits |
|---|---|---|
| LookFantastic · Google | daily | ~72 |
| LookFantastic · Meta | weekly | ~5 |
| John Lewis, Boots | monthly | ~15 |

**Use `--days 7`, not `--days 1`.** A 1-day window is throttled by Google to
~900 results and was verified to drop 1,077 ads that were live that same day.
A 7-day window returns ~8,000 and reaches the ceiling; 14 and 30 days add
nothing.
