from dataclasses import dataclass, field


@dataclass(frozen=True)
class Retailer:
    slug: str
    name: str
    domain: str
    region: str = "GB"
    meta_page_id: str | None = None
    search_keywords: tuple[str, ...] = field(default_factory=tuple)


RETAILERS = {
    "lookfantastic": Retailer(
        slug="lookfantastic",
        name="LookFantastic",
        domain="lookfantastic.com",
        meta_page_id="21631697312",
        search_keywords=("lookfantastic", "lookfantastic clinique", "lookfantastic mac"),
    ),
    "johnlewis": Retailer(
        slug="johnlewis",
        name="John Lewis",
        domain="johnlewis.com",
        meta_page_id="145210795501787",
        search_keywords=("john lewis beauty", "john lewis clinique"),
    ),
    "allbeauty": Retailer(
        slug="allbeauty",
        name="allbeauty",
        domain="allbeauty.com",
        meta_page_id="159134384258861",
        search_keywords=("allbeauty clinique", "allbeauty perfume"),
    ),
    "asos": Retailer(
        slug="asos",
        name="ASOS",
        domain="asos.com",
        meta_page_id="10936503735",
        search_keywords=("asos beauty", "asos face and body"),
    ),
    "next": Retailer(
        slug="next",
        name="Next",
        domain="next.co.uk",
        meta_page_id="94971738769",
        search_keywords=("next beauty", "next fragrance"),
    ),
    "boots": Retailer(
        slug="boots",
        name="Boots",
        domain="boots.com",
        meta_page_id="137917343831",
        search_keywords=("boots beauty", "boots clinique"),
    ),
}


def get_retailer(slug: str) -> Retailer:
    try:
        return RETAILERS[slug]
    except KeyError:
        raise SystemExit(f"Unknown retailer '{slug}'. Known: {', '.join(RETAILERS)}")
