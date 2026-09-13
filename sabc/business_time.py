"""Calendar dates for project decisions use the Shanghai business day."""
from datetime import datetime
from zoneinfo import ZoneInfo


def today():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()
