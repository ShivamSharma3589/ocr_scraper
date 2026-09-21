import re

PROMO_RE = re.compile(r"\b[Cc][Oo][Dd][Ee]:?\s*([A-Z][A-Z0-9]{2,14})\b")
DISCOUNT_RE = re.compile(r"(?:up\s+to\s+)?(\d{1,3})%\s*off(?:\s+selected)?", re.I)


def parse(copy):
    text = " ".join(filter(None, [copy.get("headline"), copy.get("description")]))
    if not text:
        return []

    codes = sorted({c.upper() for c in PROMO_RE.findall(text)})
    discounts = sorted({(m.group(0).strip(), int(m.group(1))) for m in DISCOUNT_RE.finditer(text)})

    if not codes and not discounts:
        return []

    offers = []
    for code in codes or [None]:
        if discounts:
            for text_value, pct in discounts:
                offers.append({"promo_code": code, "discount_text": text_value, "discount_pct": pct})
        else:
            offers.append({"promo_code": code, "discount_text": None, "discount_pct": None})
    return offers
