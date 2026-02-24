#pytimeparse.py
"""Minimal local fallback for pytimeparse.parse used by vendored twelvedata utils."""
import re

_UNIT_SECONDS = {
    's': 1, 'sec': 1, 'secs': 1, 'second': 1, 'seconds': 1,
    'm': 60, 'min': 60, 'mins': 60, 'minute': 60, 'minutes': 60,
    'h': 3600, 'hr': 3600, 'hrs': 3600, 'hour': 3600, 'hours': 3600,
    'd': 86400, 'day': 86400, 'days': 86400,
    'w': 604800, 'wk': 604800, 'wks': 604800, 'week': 604800, 'weeks': 604800,
    'mon': 2592000, 'month': 2592000, 'months': 2592000,
    'y': 31536000, 'yr': 31536000, 'year': 31536000, 'years': 31536000,
}


def parse(value):
    if value is None:
        return None
    s = str(value).strip().lower().replace(' ', '')
    m = re.fullmatch(r'([0-9]+)([a-z]+)', s)
    if not m:
        return None
    n = int(m.group(1))
    unit = m.group(2)
    if unit in _UNIT_SECONDS:
        return n * _UNIT_SECONDS[unit]
    # handle aliases like 'mins' not already in map, or pluralized shorthand combos
    for k, sec in _UNIT_SECONDS.items():
        if unit.startswith(k):
            return n * sec
    return None
