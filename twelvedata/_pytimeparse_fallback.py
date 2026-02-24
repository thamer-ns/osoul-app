"""Tiny fallback for `pytimeparse`.

Why:
- The real dependency is listed in requirements.txt.
- But to keep the vendored SDK usable even if the dependency is missing in some
  environments, we provide a minimal parser.

It supports patterns like: "5m", "1h", "2 days", "1week" ...
Returns seconds as int, or None.
"""

from __future__ import annotations

import re


def parse(value):
    if value is None:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s.isdigit():
        return int(s)

    total = 0.0
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
