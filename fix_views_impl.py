# fix_views_impl.py
# إصلاح views_impl.py تلقائياً:
# - حذف render_navbar/router/view_dashboard
# - حذف بقايا if/elif pg == ... لو خرجت top-level
# - حذف imports المكررة (على مستوى الملف)
# - عمل backup قبل التعديل

from pathlib import Path
from datetime import datetime
import shutil
import re

TARGET = Path("views_impl.py")

if not TARGET.exists():
    raise SystemExit("❌ لم أجد views_impl.py في نفس المجلد. شغّل السكربت من جذر المشروع.")

text = TARGET.read_text(encoding="utf-8", errors="ignore")
lines = text.splitlines(True)

# helpers
def is_toplevel(line: str) -> bool:
    return bool(line) and (len(line) == len(line.lstrip()))

def starts_toplevel(line: str, prefix: str) -> bool:
    return is_toplevel(line) and line.startswith(prefix)

def find_next_toplevel_def_or_decorator(start_idx: int) -> int:
    """أقرب سطر بعد start_idx يبدأ بـ def أو @ على مستوى الملف."""
    for k in range(start_idx + 1, len(lines)):
        if starts_toplevel(lines[k], "def ") or starts_toplevel(lines[k], "@"):
            return k
    return len(lines)

def should_skip_def(def_line: str, name: str) -> bool:
    return def_line.startswith(f"def {name}(")

# patterns
re_router_if = re.compile(r'^(if|elif)\s+pg\s*==\s*["\']')
re_router_else = re.compile(r'^(else)\s*:\s*$')

# state
out = []
seen_streamlit_import = False

i = 0
while i < len(lines):
    line = lines[i]

    # 0) حذف re-export لو موجود
    if starts_toplevel(line, "from ui.router import router as router") or starts_toplevel(line, "from ui.router import render_navbar as render_navbar"):
        i += 1
        continue

    # 1) إزالة import streamlit المكرر على مستوى الملف
    if starts_toplevel(line, "import streamlit as st"):
        if not seen_streamlit_import:
            seen_streamlit_import = True
            out.append(line)
        # إذا مكرر (top-level) تجاهله
        i += 1
        continue

    # 2) التعامل مع decorators @... قبل def
    if starts_toplevel(line, "@"):
        # اجمع الديكوراتورز
        dec_start = i
        j = i
        while j < len(lines) and starts_toplevel(lines[j], "@"):
            j += 1

        # إذا بعدها def
        if j < len(lines) and starts_toplevel(lines[j], "def "):
            def_line = lines[j]
            # لو الدالة مستهدفة للحذف
            if should_skip_def(def_line, "render_navbar") or should_skip_def(def_line, "router") or should_skip_def(def_line, "view_dashboard"):
                # تجاهل من بداية decorators حتى نهاية بلوك الدالة
                end = find_next_toplevel_def_or_decorator(j)
                i = end
                continue
            else:
                # ليست مستهدفة: انزل الديكوراتورز عادي
                out.extend(lines[dec_start:j])
                i = j
                continue
        else:
            # ديكور بدون def بعدها: مرّره كما هو
            out.append(line)
            i += 1
            continue

    # 3) حذف الدوال المستهدفة مباشرة
    if starts_toplevel(line, "def "):
        if should_skip_def(line, "render_navbar") or should_skip_def(line, "router") or should_skip_def(line, "view_dashboard"):
            end = find_next_toplevel_def_or_decorator(i)
            i = end
            continue

    # 4) حذف أي بقايا Router خرجت top-level: if/elif pg == ...
    if is_toplevel(line) and re_router_if.match(line.strip()):
        # احذف حتى أقرب def/@ على مستوى الملف
        end = find_next_toplevel_def_or_decorator(i)
        i = end
        continue

    # أحيانًا بقايا router تبدأ بأسطر تمهيدية top-level:
    # pg = st.session_state.page / fin = calculate_portfolio_metrics / render_navbar()
    if is_toplevel(line) and (
        line.startswith("pg = st.session_state.page")
        or line.startswith("pg = st.session_state.get(")
        or line.startswith("fin = calculate_portfolio_metrics")
        or line.strip() == "render_navbar()"
        or line.strip() == "_ensure_ui_once()"
        or line.strip().startswith('if "page" not in st.session_state')
        or line.strip().startswith("st.session_state.page")
    ):
        # لو بعدها مباشرة if/elif pg == ... غالباً هذا جسم router خرج
        # نحذف هذا السطر أيضاً، ثم نستمر نحذف لو لحقته chain
        i += 1
        # ثم احذف أي chain تالية حتى def/@
        # (نواصل إزالة سطور top-level حتى نصل لتعريف دالة جديدة/ديكور)
        while i < len(lines) and not (starts_toplevel(lines[i], "def ") or starts_toplevel(lines[i], "@")):
            # لو وصلنا لسطر فارغ أو تعليق فقط، ما يضر
            # لكن نكمل الحذف طالما نحن خارج def
            i += 1
        continue

    # default keep
    out.append(line)
    i += 1

new_text = "".join(out)

# backup
backup = TARGET.with_suffix(".py.bak_" + datetime.now().strftime("%Y%m%d_%H%M%S"))
shutil.copy2(TARGET, backup)

TARGET.write_text(new_text, encoding="utf-8")

print("✅ تم إصلاح views_impl.py بنجاح")
print(f"🧾 Backup: {backup.name}")

