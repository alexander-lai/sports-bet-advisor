"""Small parsing and normalisation helpers."""
import re
import unicodedata
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from .errors import AppError

EASTERN = ZoneInfo("America/New_York")
NAME_SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v"}


def utcnow():
    return datetime.now(timezone.utc)


def today_et():
    """NBA slates are scheduled on US Eastern dates."""
    return datetime.now(EASTERN).date()


def to_eastern_date(iso_ts):
    ts = datetime.fromisoformat(iso_ts.replace("Z", "+00:00"))
    return ts.astimezone(EASTERN).date()


def normalize_name(name):
    """'Luka Dončić' / 'Jaren Jackson Jr.' -> comparable lowercase key."""
    ascii_name = (
        unicodedata.normalize("NFKD", name or "")
        .encode("ascii", "ignore")
        .decode()
    )
    cleaned = re.sub(r"[^a-z ]", "", ascii_name.lower().replace("-", " "))
    parts = [p for p in cleaned.split() if p not in NAME_SUFFIXES]
    return " ".join(parts)


def parse_date(value):
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise AppError(f"Invalid date: {value!r}") from exc


def parse_float(value, name, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise AppError(f"{name} must be a number") from exc
    if minimum is not None and number < minimum:
        raise AppError(f"{name} must be >= {minimum}")
    if maximum is not None and number > maximum:
        raise AppError(f"{name} must be <= {maximum}")
    return number


def parse_minutes(raw):
    """Ball Don't Lie reports minutes as '34', '34:12' or ''."""
    if raw in (None, ""):
        return 0.0
    text = str(raw)
    if ":" in text:
        mins, secs = text.split(":", 1)
        try:
            return int(mins) + int(secs or 0) / 60.0
        except ValueError:
            return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0
