"""Read ad copy out of a rendered Google search-ad screenshot.

Google renders headlines and sitelink titles in blue and body text in grey, so
word colour separates them where layout alone cannot.
"""

import io
import re
from collections import OrderedDict

import pytesseract
from PIL import Image

STOP_RE = re.compile(r"^(sponsored|rating for|return policy|most items|\d[.,]\d\s)", re.I)


def _is_blue(rgb):
    red, green, blue = rgb
    return blue - max(red, green) > 25 and blue > 80


def _ink_colour(image, box):
    crop = image.crop(box).convert("RGB")
    pixels = list(crop.getdata())
    if not pixels:
        return (0, 0, 0)
    ink = sorted(pixels, key=sum)[: max(1, len(pixels) // 4)]
    return tuple(sum(channel) // len(ink) for channel in zip(*ink))


def _lines(image):
    data = pytesseract.image_to_data(
        image, config="--psm 6", output_type=pytesseract.Output.DICT
    )

    grouped = OrderedDict()
    for i, text in enumerate(data["text"]):
        if not text.strip() or int(data["conf"][i]) < 40:
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        box = (
            data["left"][i],
            data["top"][i],
            data["left"][i] + data["width"][i],
            data["top"][i] + data["height"][i],
        )
        grouped.setdefault(key, []).append((text, box))

    lines = []
    for words in grouped.values():
        blues = sum(1 for _, box in words if _is_blue(_ink_colour(image, box)))
        lines.append({
            "text": " ".join(word for word, _ in words),
            "blue": blues > len(words) / 2,
        })
    return lines


def extract(image_bytes):
    image = Image.open(io.BytesIO(image_bytes))
    image = image.resize((image.width * 2, image.height * 2), Image.LANCZOS)

    lines = _lines(image)
    blue_at = [i for i, line in enumerate(lines) if line["blue"]]
    if not blue_at:
        return None

    start = end = blue_at[0]
    while end + 1 < len(lines) and lines[end + 1]["blue"]:
        end += 1

    header = [l["text"] for l in lines[:start] if not STOP_RE.match(l["text"])]
    headline = " ".join(l["text"] for l in lines[start : end + 1])

    cursor = end + 1
    description = []
    while cursor < len(lines):
        if lines[cursor]["blue"] or STOP_RE.match(lines[cursor]["text"]):
            break
        description.append(lines[cursor]["text"])
        cursor += 1

    sitelinks = []
    while cursor < len(lines):
        if not lines[cursor]["blue"]:
            cursor += 1
            continue
        title, cursor = lines[cursor]["text"], cursor + 1
        body = []
        while cursor < len(lines) and not lines[cursor]["blue"]:
            if not STOP_RE.match(lines[cursor]["text"]):
                body.append(lines[cursor]["text"])
            cursor += 1
        sitelinks.append({"title": title, "description": " ".join(body) or None})

    description_text = " ".join(description).strip()

    return {
        "extraction_source": "ocr",
        "headline": headline.strip() or None,
        "description": description_text or None,
        "display_url": next((t for t in header if "." in t and " " not in t.strip()), None),
        "sitelinks": sitelinks,
        "raw_text": "\n".join(l["text"] for l in lines),
        "is_truncated": description_text.endswith("..."),
    }
