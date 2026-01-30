import streamlit as st
import pandas as pd
import html
import math
import re

# ============================================================
# 🧼 Helpers: Safe parsing/formatting
# ============================================================

_NUM_RE = re.compile(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?")

def _is_nan(x) -> bool:
    try:
        return x is None or (isinstance(x, float) and math.isnan(x))
    except Exception:
        return x is None

def _safe_number(val, default=None):
    """
    يحاول تحويل أي قيمة إلى float بأمان.
    يدعم:
    - "1,234.50"
    - "SAR 12.3"
    - "12.3%" (يرجع 12.3)
    - "(500)" (يرجع -500)
    - None/NaN/inf
    """
    if val is None:
        return default
    try:
        # pandas/numpy
        if hasattr(pd, "isna") and pd.isna(val):
            return default
    except Exception:
        pass

    # لو رقم جاهز
    try:
        if isinstance(val, (int, float)) and not _is_nan(val):
            if isinstance(val, float) and (math.isinf(val)):
                return default
            return float(val)
    except Exception:
        pass

    s = str(val).strip()
    if not s:
        return default

    # أقواس سالب
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]

    # إزالة العملات/الفواصل/النسب
    s = s.replace(",", "")
    s = s.replace("SAR", "").replace("ر.س", "").replace("ريال", "")
    s = s.replace("%", "").strip()

    m = _NUM_RE.search(s)
    if not m:
        return default
    try:
        x = float(m.group(0))
        if math.isinf(x) or math.isnan(x):
            return default
        return x
    except Exception:
        return default

def safe_fmt(val, suffix=""):
    """
    موجودة سابقاً — تم تحسينها بدون تغيير توقيعها.
    """
    try:
        x = _safe_number(val, default=None)
        if x is None:
            return "-"
        return f"{x:,.2f}{suffix}"
    except Exception:
        return "-"

def _fmt_percent(val, digits=2):
    x = _safe_number(val, default=None)
    if x is None:
        return "-"
    return f"{x:.{digits}f}%"

def _fmt_money(val, digits=2, suffix=""):
    x = _safe_number(val, default=None)
    if x is None:
        return "-"
    return f"{x:,.{digits}f}{suffix}"

def _safe_text(val) -> str:
    if val is None:
        return "-"
    try:
        if hasattr(pd, "isna") and pd.isna(val):
            return "-"
    except Exception:
        pass
    s = str(val)
    if not s.strip():
        return "-"
    return s

def _short_date(val) -> str:
    s = _safe_text(val)
    # قص أول 10 أحرف إذا كان تاريخ ISO
    return s[:10] if len(s) >= 10 else s


# ============================================================
# 🎨 Optional: Inject CSS styles once
# ============================================================

def inject_component_styles():
    """
    اختياري: استدعِ هذه الدالة مرة في app.py أو views.py
    لتضمن وجود ستايلات الـ KPI والجدول حتى لو ما عندك CSS خارجي.
    """
    st.markdown(
        """
        <style>
        .kpi-card{
            background: #ffffff;
            border: 1px solid rgba(148,163,184,0.25);
            border-radius: 16px;
            padding: 14px;
            box-shadow: 0 1px 6px rgba(15,23,42,0.06);
            position: relative;
            overflow: hidden;
        }
        .kpi-icon-bg{
            position:absolute;
            top:10px;
            left:10px;
            width:34px;height:34px;
            display:flex;align-items:center;justify-content:center;
            background: rgba(37,99,235,0.08);
            border-radius: 12px;
            font-size: 18px;
        }
        .kpi-label{
            margin-top: 4px;
            color:#64748B;
            font-weight:700;
            font-size: 0.85rem;
        }
        .kpi-value{
            color:#0F172A;
            font-weight: 900;
            font-size: 1.4rem;
            margin-top: 6px;
            direction:ltr;
            text-align:left;
        }
        .finance-table{
            width:100%;
            border-collapse: separate;
            border-spacing: 0;
            background:#fff;
            border:1px solid rgba(148,163,184,0.25);
            border-radius:14px;
            overflow:hidden;
        }
        .finance-table th{
            background: #F8FAFC;
            color:#334155;
            font-weight:800;
            font-size:0.85rem;
            padding:10px;
            text-align:right;
            border-bottom:1px solid rgba(148,163,184,0.25);
            white-space:nowrap;
        }
        .finance-table td{
            padding:10px;
            border-bottom:1px solid rgba(148,163,184,0.15);
            color:#0F172A;
            font-weight:600;
            font-size:0.85rem;
            white-space:nowrap;
            text-align:right;
        }
        .finance-table tr:hover td{
            background: rgba(37,99,235,0.04);
        }
        .txt-green{ color:#059669; font-weight:800;}
        .txt-red{ color:#DC2626; font-weight:800;}
        .txt-blue{ color:#2563EB; font-weight:800;}
        .txt-muted{ color:#64748B; font-weight:700;}
        .td-num{ direction:ltr; text-align:left; }
        .badge{
            display:inline-block;
            padding:2px 10px;
            border-radius:999px;
            font-weight:800;
            font-size:0.75rem;
        }
        .badge-open{ background:#DCFCE7; color:#166534; }
        .badge-closed{ background:#FEE2E2; color:#991B1B; }
        .link{
            color:#2563EB;
            text-decoration:none;
            font-weight:800;
        }
        .link:hover{ text-decoration:underline; }
        </style>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# 🧾 KPI Cards
# ============================================================

def render_kpi(label, value, color_class="neutral", icon="📊"):
    """
    نفس الدالة السابقة — تحسينات: أمان أكثر + قيمة تُعرض كما هي (مع escaping عند النص).
    """
    val_color = "#1E293B"
    if color_class == "success":
        val_color = "#059669"
    elif color_class == "danger":
        val_color = "#DC2626"
    elif color_class == "blue":
        val_color = "#2563EB"

    safe_label = html.escape(_safe_text(label))
    # لا نهرب value لو كان رقم منسّق أنت، لكن لو نص نأمنه
    v = value
    if isinstance(value, str):
        v = html.escape(value)
    else:
        v = html.escape(_safe_text(value))

    st.markdown(
        f"""
        <div class="kpi-card">
            <div class="kpi-icon-bg">{html.escape(_safe_text(icon))}</div>
            <div class="kpi-label">{safe_label}</div>
            <div class="kpi-value" style="color:{val_color}!important;">{v}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_ticker_card(symbol, name, price, change):
    """
    نفس الدالة السابقة — تحسين parsing للتغيير والسعر + عرض آمن.
    """
    chg = _safe_number(change, default=0.0) or 0.0
    col = "#059669" if chg >= 0 else "#DC2626"
    bg = "#DCFCE7" if chg >= 0 else "#FEE2E2"

    p = _safe_number(price, default=None)
    price_disp = f"{p:,.2f}" if p is not None else "-"

    change_disp = f"{chg:+.2f}%"

    sym_disp = html.escape(_safe_text(symbol))
    name_disp = html.escape(_safe_text(name))

    st.markdown(
        f"""
        <div class="kpi-card" style="padding:15px;min-height:120px;">
            <div style="display:flex;justify-content:space-between;margin-bottom:10px;gap:10px;">
                <div style="font-weight:900;color:#1E293B;direction:ltr;text-align:left;">{sym_disp}</div>
                <div style="direction:ltr;color:{col};background:{bg};padding:2px 8px;border-radius:8px;font-weight:800;font-size:0.8rem;">
                    {change_disp}
                </div>
            </div>
            <div style="font-size:1.5rem;font-weight:900;color:#0F172A;direction:ltr;text-align:left;">{price_disp}</div>
            <div style="color:#94A3B8;font-size:0.75rem;font-weight:600;">{name_disp}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ============================================================
# 📋 Custom Table
# ============================================================

def render_custom_table(df, columns_config):
    """
    columns_config يدعم شكلين:
    1) القديم: (col_key, label, col_type)
    2) الجديد: (col_key, label, col_type, format_func)
       format_func(val, row) -> (display_str, css_class)
    col_type المدعومة:
      - money / percent / colorful / badge / date
      - text / number / bool / auto / link
    """
    if df is None or df.empty:
        st.info("📭 لا توجد بيانات متاحة")
        return

    # بداية الجدول
    html_out = '<div style="overflow-x:auto;"><table class="finance-table"><thead><tr>'

    # الرؤوس
    for cfg in columns_config:
        # دعم config القديم/الجديد
        try:
            _, label, _ = cfg[0], cfg[1], cfg[2]
        except Exception:
            label = ""
        html_out += f'<th>{html.escape(_safe_text(label))}</th>'
    html_out += "</tr></thead><tbody>"

    for _, row in df.iterrows():
        html_out += "<tr>"

        for cfg in columns_config:
            # unpack
            col_key = cfg[0]
            label = cfg[1] if len(cfg) > 1 else col_key
            col_type = cfg[2] if len(cfg) > 2 else "auto"
            format_func = cfg[3] if len(cfg) > 3 else None

            val = row.get(col_key, "")

            # custom formatter أولاً
            if callable(format_func):
                try:
                    disp, cls = format_func(val, row)
                    disp = html.escape(_safe_text(disp)) if not (isinstance(disp, str) and disp.strip().startswith("<")) else disp
                    cls = _safe_text(cls) if cls else ""
                    html_out += f'<td><span class="{html.escape(cls)}">{disp}</span></td>'
                    continue
                except Exception:
                    # لو فشل formatter نكمل للمعالجة العادية
                    pass

            display = _safe_text(val)
            cls = ""
            td_cls = ""

            if col_type in ("money",):
                x = _safe_number(val, default=None)
                display = _fmt_money(x) if x is not None else "-"
                cls = "txt-blue" if (x is not None and x > 0) else ""
                td_cls = "td-num"

            elif col_type in ("percent",):
                x = _safe_number(val, default=None)
                display = _fmt_percent(x) if x is not None else "-"
                cls = "txt-green" if (x is not None and x >= 0) else "txt-red"
                td_cls = "td-num"

            elif col_type in ("colorful",):
                x = _safe_number(val, default=None)
                display = _fmt_money(x) if x is not None else "-"
                cls = "txt-green" if (x is not None and x >= 0) else "txt-red"
                td_cls = "td-num"

            elif col_type in ("number",):
                x = _safe_number(val, default=None)
                display = f"{x:,.2f}" if x is not None else "-"
                td_cls = "td-num"

            elif col_type in ("bool",):
                s = str(val).strip().lower()
                truthy = s in ("1", "true", "yes", "y", "نعم", "صح") or val is True
                display = "✅" if truthy else "—"
                cls = "txt-green" if truthy else "txt-muted"

            elif col_type in ("badge",):
                s = str(val).lower()
                is_op = s.startswith("open") or s.startswith("مفتوح")
                badge_cls = "badge-open" if is_op else "badge-closed"
                badge_text = "مفتوحة" if is_op else "مغلقة"
                display = f'<span class="badge {badge_cls}">{badge_text}</span>'
                html_out += f"<td>{display}</td>"
                continue

            elif col_type in ("date",):
                display = _short_date(val)
                cls = "txt-muted"

            elif col_type in ("link",):
                # يتوقع val يكون URL أو (text,url)
                url = None
                text = None
                if isinstance(val, (tuple, list)) and len(val) >= 2:
                    text, url = val[0], val[1]
                else:
                    url = str(val) if val else ""
                    text = url
                url = (url or "").strip()
                text = _safe_text(text)
                if url.startswith("http"):
                    display = f'<a class="link" href="{html.escape(url)}" target="_blank">{html.escape(text)}</a>'
                    html_out += f"<td>{display}</td>"
                    continue
                display = html.escape(text)

            elif col_type in ("text",):
                display = html.escape(_safe_text(val))

            elif col_type in ("auto",):
                # إذا رقم -> رقم، إذا تاريخ -> قص، وإلا نص
                x = _safe_number(val, default=None)
                if x is not None:
                    display = f"{x:,.2f}"
                    td_cls = "td-num"
                else:
                    display = html.escape(_short_date(val))

            else:
                display = html.escape(_safe_text(val))

            # Sanitization Final Step (لو ما كان HTML جاهز)
            if not (isinstance(display, str) and display.strip().startswith("<")):
                display = html.escape(_safe_text(display))

            html_out += f'<td class="{html.escape(td_cls)}"><span class="{html.escape(cls)}">{display}</span></td>'

        html_out += "</tr>"

    html_out += "</tbody></table></div>"
    st.markdown(html_out, unsafe_allow_html=True)