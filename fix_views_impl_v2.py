# fix_views_impl_v2.py
# Fix views_impl.py using robust markers + safe fallbacks.
# - removes Navigation + Dashboard blocks from views_impl.py
# - removes Router block from views_impl.py (and anything after it)
# - removes leftover router if/elif chain that might be top-level
# - removes duplicate "import streamlit as st" on top-level
# - makes a timestamped backup first

from pathlib import Path
from datetime import datetime
import shutil
import re

p = Path("views_impl.py")
if not p.exists():
    raise SystemExit("❌ views_impl.py غير موجود في هذا المسار. شغّل السكربت من جذر المشروع.")

txt = p.read_text(encoding="utf-8", errors="ignore")
lines = txt.splitlines(True)

def find_line_index(pattern: str):
    for i, ln in enumerate(lines):
        if pattern in ln:
            return i
    return None

def remove_range(a: int, b: int):
    # remove lines [a, b)
    del lines[a:b]

# ✅ 1) Remove Navigation+Dashboard blocks based on markers
i_nav = find_line_index("# 1) Navigation")
i_port = find_line_index("# 3) Portfolio View")
if i_nav is not None and i_port is not None and i_nav < i_port:
    remove_range(i_nav, i_port)

# ✅ 2) Remove Router block to end (this is where your error is coming from)
i_router = find_line_index("# 9) Router")
if i_router is not None:
    remove_range(i_router, len(lines))

# ✅ 3) Fallback: remove any top-level router chain that escaped (if/elif pg == ...)
out = []
router_chain_re = re.compile(r'^\s*(if|elif)\s+pg\s*==\s*["\']')
in_bad_chain = False

for ln in lines:
    # start of bad chain at top-level
    if ln and (len(ln) == len(ln.lstrip())) and router_chain_re.match(ln):
        in_bad_chain = True
        continue
    # stop removing once we reach a top-level def or decorator
    if in_bad_chain and ln and (len(ln) == len(ln.lstrip())) and (ln.startswith("def ") or ln.startswith("@")):
        in_bad_chain = False

    if in_bad_chain:
        continue

    out.append(ln)

lines = out

# ✅ 4) Remove duplicate top-level "import streamlit as st" (keep first only)
out = []
seen = False
for ln in lines:
    if ln and (len(ln) == len(ln.lstrip())) and ln.startswith("import streamlit as st"):
        if not seen:
            seen = True
            out.append(ln)
        else:
            continue
    else:
        out.append(ln)
lines = out

new_txt = "".join(lines)

# backup
bak = p.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
shutil.copy2(p, bak)

p.write_text(new_txt, encoding="utf-8")
print("✅ تم إصلاح views_impl.py بنجاح")
print("🧾 Backup:", bak.name)

