from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone


@dataclass
class Creative:
    platform: str
    platform_creative_id: str
    format: str | None = None
    advertiser_id: str | None = None
    advertiser_name: str | None = None
    first_shown: datetime | None = None
    last_shown: datetime | None = None
    total_days_shown: int | None = None
    details_url: str | None = None
    media_url: str | None = None
    preview_link: str | None = None
    copy: dict | None = None
    platform_details: dict = field(default_factory=dict)
    raw: dict = field(default_factory=dict)


def window(days):
    today = date.today()
    return today - timedelta(days=max(days, 1) - 1), today + timedelta(days=1)


def to_datetime(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return datetime.fromtimestamp(value, timezone.utc).replace(tzinfo=None)
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text).replace(tzinfo=None)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"):
            try:
                return datetime.strptime(str(value)[:19], fmt)
            except ValueError:
                continue
    return None
