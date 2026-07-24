from datetime import datetime
import uuid
from .uuid7 import generate_uuid7
import pytz
from app.config import settings


def get_tz():
    return pytz.timezone(settings.TIMEZONE)


def generate_uuid() -> uuid.UUID:
    return generate_uuid7()

def now() -> datetime:
    return datetime.now(get_tz())


def clean_agency_ids(raw) -> list[str]:
    """Flatten a message's ``agency_ids`` into clean single-UUID strings.

    Legacy rows can hold a single comma-joined element (e.g. ``["id1,id2"]``);
    feeding that raw into a UUID query crashes asyncpg. Split on commas and
    drop blanks so every id is a lone UUID.
    """
    return [
        part.strip()
        for item in raw or []
        for part in str(item).split(",")
        if part.strip()
    ]