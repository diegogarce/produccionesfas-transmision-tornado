import pymysql
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from app.config import MYSQL_CONFIG


DEFAULT_APP_TIMEZONE = "America/Mexico_City"


def _get_target_timezone(tz_name: str | None):
    """Best-effort timezone resolver.

    If IANA tz data is unavailable (common on Windows or minimal images), ZoneInfo
    may raise. In that case we fall back to UTC rather than crashing.
    """
    if tz_name:
        try:
            return ZoneInfo(str(tz_name))
        except Exception:
            pass

    try:
        return ZoneInfo(DEFAULT_APP_TIMEZONE)
    except Exception:
        return timezone.utc


def get_mexico_city_time():
    # Backwards-compatible helper used across the app.
    return now_in_timezone(DEFAULT_APP_TIMEZONE)


def now_in_timezone(tz_name: str | None) -> datetime:
    tz = _get_target_timezone(tz_name)
    return datetime.now(tz)


def now_hhmm_in_timezone(tz_name: str | None) -> str:
    return now_in_timezone(tz_name).strftime("%H:%M")


def create_db_connection():
    connection = pymysql.connect(**MYSQL_CONFIG)
    # Keep DB timestamps in UTC; convert to local time in the app layer.
    with connection.cursor() as cursor:
        try:
            cursor.execute("SET time_zone = '+00:00'")
        except Exception:
            # If the server blocks changing session tz, we still treat values as UTC.
            pass
    connection.autocommit(True)
    return connection


def _normalize_timestamps(row):
    if not row:
        return row

    tz_name = row.get("timezone") or DEFAULT_APP_TIMEZONE
    target_tz = _get_target_timezone(tz_name)

    normalized = row.copy()
    for key, value in row.items():
        if isinstance(value, datetime):
            # PyMySQL returns naive datetime for DATETIME columns.
            # We store and interpret these as UTC, then convert for display.
            utc_aware = value.replace(tzinfo=timezone.utc)
            normalized[key] = utc_aware.astimezone(target_tz).strftime("%Y-%m-%d %H:%M")
    return normalized
