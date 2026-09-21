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
    "boots": Retailer(
        slug="boots",
        name="Boots",
        domain="boots.com",
        meta_page_id=None,
        search_keywords=("boots beauty", "boots clinique"),
    ),
}


def get_retailer(slug: str) -> Retailer:
    try:
        return RETAILERS[slug]
    except KeyError:
        raise SystemExit(f"Unknown retailer '{slug}'. Known: {', '.join(RETAILERS)}")
