import re

PROMO_RE = re.compile(r"\b[Cc][Oo][Dd][Ee]:?\s*([A-Z][A-Z0-9]{2,14})\b")
DISCOUNT_RE = re.compile(r"(?:up\s+to\s+)?(\d{1,3})%\s*off(?:\s+selected)?", re.I)


def _discounts(text):
    """Unique discounts, deduped case-insensitively.

    MySQL compares these with a case-insensitive collation, so "30% Off" and
    "30% off" must collapse here or the unique index rejects the second row.
    """
    found = {}
    for match in DISCOUNT_RE.finditer(text):
        phrase = " ".join(match.group(0).split())
        found.setdefault(phrase.lower(), (phrase, int(match.group(1))))
    return sorted(found.values())


def parse(copy):
    text = " ".join(filter(None, [copy.get("headline"), copy.get("description")]))
    if not text:
        return []

    codes = sorted({c.upper() for c in PROMO_RE.findall(text)})
    discounts = _discounts(text)

    if not codes and not discounts:
        return []

    offers = []
    for code in codes or [None]:
        if discounts:
            for phrase, pct in discounts:
                offers.append({"promo_code": code, "discount_text": phrase,
                               "discount_pct": pct})
        else:
            offers.append({"promo_code": code, "discount_text": None,
                           "discount_pct": None})
    return offers
