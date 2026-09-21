"""Classify an ad as brand, category or generic.

Brand wins over category because "Clinique Moisturiser" is a brand campaign
that happens to name a category.
"""

from adintel.classification.brands import match, normalise
from adintel.config.brands import CATEGORY_TERMS

BRAND = "brand"
CATEGORY = "category"
GENERIC = "generic"


def classify(headline, known_brands=None):
    if not headline:
        return GENERIC

    if known_brands or match(headline):
        return BRAND

    text = normalise(headline)
    if any(term in text for term in CATEGORY_TERMS):
        return CATEGORY

    return GENERIC
