"""Decode the gzipped protobuf blob Google hides in creative preview links."""

import base64
import gzip
import re
import urllib.parse

URL_RE = re.compile(rb"https?://[\x20-\x7e]{6,200}")


def _read_varint(buf, index):
    value = shift = 0
    while True:
        byte = buf[index]
        index += 1
        value |= (byte & 0x7F) << shift
        if not byte & 0x80:
            return value, index
        shift += 7


def field_values(blob, name):
    key = b"\n" + bytes([len(name)]) + name
    found, position = [], blob.find(key)

    while position != -1:
        index = position + len(key)
        if blob[index : index + 1] == b"\x12":
            index += 1
            _, index = _read_varint(blob, index)
            if blob[index : index + 1] == b"\n":
                index += 1
                length, index = _read_varint(blob, index)
                found.append(blob[index : index + length].decode("utf-8", "replace"))
        position = blob.find(key, position + 1)

    return found


def decode(link):
    query = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
    for key in ("overlay", "assets"):
        if key in query:
            encoded = query[key][0].lstrip("=")
            padded = encoded + "=" * (-len(encoded) % 4)
            return key, gzip.decompress(base64.urlsafe_b64decode(padded))
    return None, None


def text_copy(link):
    _, blob = decode(link)
    if not blob:
        return None

    headlines = field_values(blob, b"headline")
    if not headlines:
        return None

    descriptions = field_values(blob, b"description")
    display_urls = field_values(blob, b"visurl")

    return {
        "extraction_source": "overlay",
        "headline": headlines[0],
        "description": descriptions[0] if descriptions else None,
        "display_url": display_urls[0] if display_urls else None,
        "sitelinks": [],
    }


def shopping_copy(link, is_shopping):
    param, blob = decode(link)
    if not blob:
        return None

    providers = field_values(blob, b"cssDisplayString")

    urls = []
    for match in URL_RE.findall(blob):
        url = re.split(r"[\x00-\x1f(]", match.decode("utf-8", "replace"))[0].rstrip("&")
        if url not in urls:
            urls.append(url)

    return {
        "extraction_source": "shopping" if is_shopping else "video",
        "headline": None,
        "description": None,
        "display_url": None,
        "landing_url": urls[0] if urls else None,
        "css_provider": providers[0] if providers else None,
        "overlay_param": param,
        "sitelinks": [],
    }
