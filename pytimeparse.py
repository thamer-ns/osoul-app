"""Minimal local fallback for pytimeparse used by vendored twelvedata."""
import re

def parse(value):
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s.isdigit():
        return int(s)
    total = 0
    matched = False
    for num, unit in re.findall(r"([0-9]+(?:\.[0-9]+)?)\s*([a-z]+)", s):
        matched = True
        n = float(num)
        if unit.startswith(("s", "sec")):
            total += n
        elif unit.startswith(("m", "min")):
            total += n * 60
        elif unit.startswith(("h", "hr")):
            total += n * 3600
        elif unit.startswith(("d", "day")):
            total += n * 86400
        elif unit.startswith(("w", "week")):
            total += n * 604800
    return int(total) if matched else None
