import re
import unicodedata

from adintel.config.brands import BRANDS

PATTERNS = {name: re.compile(pattern) for name, pattern in BRANDS.items()}


def normalise(text):
    decomposed = unicodedata.normalize("NFKD", text or "")
    stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped.lower()).strip()


def match(headline):
    text = normalise(headline)
    return [name for name, pattern in PATTERNS.items() if pattern.search(text)]
