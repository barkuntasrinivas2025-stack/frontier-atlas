import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from dateutil import parser

def parse_publication_date(value, *, now: datetime | None = None) -> datetime | None:
    if not value: return None
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    s=str(value).strip().lower()
    m=re.fullmatch(r'(\d+)\s+(minute|minutes|hour|hours|day|days)\s+ago',s)
    if m:
        n=int(m.group(1)); unit=m.group(2); return now-timedelta(**({'minutes':n} if unit.startswith('minute') else {'hours':n} if unit.startswith('hour') else {'days':n}))
    try:
        dt=parsedate_to_datetime(str(value))
    except Exception:
        try: dt=parser.parse(str(value))
        except Exception: return None
    if dt.tzinfo is None: dt=dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)

def is_within_previous_24h(dt: datetime, *, now: datetime | None=None) -> bool:
    now=(now or datetime.now(timezone.utc)).astimezone(timezone.utc); dt=dt.astimezone(timezone.utc)
    return now-timedelta(hours=24) <= dt <= now
