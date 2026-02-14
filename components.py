# components.py
import streamlit as st
import pandas as pd
import html
import math
import re
import os
import base64
import textwrap
from typing import Any, Dict, List, Optional, Tuple


# ============================================================
# ✅ Arabic UI Translation helpers
# ============================================================

_TR_MAP = {
    "Score": "الدرجة",
    "Confidence": "الثقة",
    "Pass": "ناجح",
    "Fail": "فشل",
    "Issues": "المشكلات",
    "Evidence": "الأدلة",
    "Source": "المصدر",
    "Updated": "آخر تحديث",
    "Last update": "آخر تحديث",
    "Annual": "سنوي",
    "Quarterly": "ربع سنوي",
    "TTM": "آخر 12 شهر (TTM)",
    "Buy": "شراء",
    "Sell": "بيع",
    "Hold": "احتفاظ",
    "Strong Buy": "شراء قوي",
    "Strong Sell": "بيع قوي",
    "Neutral": "محايد",
    "Bullish": "إيجابي",
    "Bearish": "سلبي",
    "Signals": "الإشارات",
    "Features": "الخصائص",
    "Backtest": "اختبار رجعي",
}

def tr(text: str) -> str:
    """ترجمة خفيفة للنصوص الشائعة (مع fallback)."""
    if text is None:
        return ""
    s = str(text)
    return _TR_MAP.get(s, s)

def fmt_sar_compact(value: float | int | None, unit: str = "SAR") -> str:
    """تنسيق رقم مالي بشكل واضح (ألف/مليون/مليار)"""
    try:
        if value is None:
            return "—"
        v = float(value)
    except Exception:
        return "—"
    sign = "-" if v < 0 else ""
    v = abs(v)
    if v >= 1_000_000_000:
        return f"{sign}{v/1_000_000_000:.2f} مليار {unit}"
    if v >= 1_000_000:
        return f"{sign}{v/1_000_000:.2f} مليون {unit}"
    if v >= 1_000:
        return f"{sign}{v/1_000:.2f} ألف {unit}"
    return f"{sign}{v:,.0f} {unit}"

# ============================================================
# ✅ App Header helpers (Fail-safe)
# ============================================================

def _img_to_base64(path: str) -> Optional[str]:
    """Return base64 for image at `path` or None if not available."""
    try:
        if not path or not os.path.exists(path):
            return None
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return None




def render_app_header(
    title: str,
    subtitle: str = "منصة تحليل الأسهم — مالي، فني، كلاسيكي، وإدارة مخاطر",
    logo_full_path: str = "assets/logo_full.png",
    logo_mark_path: str = "assets/logo_mark.png",
    # ⚠️ تركنا الخيار للتوافق الخلفي
    show_in_sidebar: bool = False,
):
    """Render a lightweight, professional header (fail-safe).

    ملاحظة: كان يظهر الـHTML كنص بسبب مسافات بادئة داخل Markdown.
    نعالج ذلك عبر `textwrap.dedent` + توحيد أسماء الـCSS classes مع styles.py.
    """
    try:
        _ = show_in_sidebar

        # Resolve logo path relative to this file
        base_dir = os.path.dirname(__file__)
        full_path = logo_full_path
        if full_path and not os.path.isabs(full_path):
            full_path = os.path.join(base_dir, full_path)

        b64 = _img_to_base64(full_path) if full_path else None
        logo_html = (
            f"<div class='os-h-logo'><img src='data:image/png;base64,{b64}' alt='logo'/></div>" if b64 else ""
        )

        html_block = textwrap.dedent(
            f"""
            <div class='os-app-header'>
              <div class='os-h-left'>
                {logo_html}
                <div>
                  <div class='os-h-title'>{html.escape(title)}</div>
                  <div class='os-h-sub'>{html.escape(subtitle)}</div>
                </div>
              </div>
              <div class='os-h-right'>
                <span class='os-chip os-chip-blue'><span class='mi'>insights</span>تحليل</span>
                <span class='os-chip os-chip-gray'><span class='mi'>shield</span>مخاطر</span>
              </div>
            </div>
            """
        ).strip()

        st.markdown(html_block, unsafe_allow_html=True)
    except Exception:
        try:
            st.markdown(f"### {title}")
        except Exception:
            pass

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
        if hasattr(pd, "isna") and pd.isna(val):
            return default
    except Exception:
        pass

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

    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]

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
    # Defensive: بعض البيئات قد تعيد تحميل الموديول جزئياً
    global _NUM_RE
    try:
        _NUM_RE
    except NameError:
        import re as _re
        _NUM_RE = _re.compile(r"^-?\\d+(?:\\.\\d+)?$")

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
    return s[:10] if len(s) >= 10 else s


# ============================================================
# 🌍 Streamlit UI Arabic Helpers (Fix English placeholders)
# ============================================================

def inject_streamlit_ar_i18n(enable: bool = True):
    """
    ✅ Best-effort DOM translation لبعض عبارات Streamlit الافتراضية:
    Choose an option / Search / No options...
    - لا يحذف شيء
    - يشتغل مرة واحدة فقط
    - قد يحتاج تحديث لو Streamlit غيّر DOM (نادر)
    """
    if not enable:
        return

    key = "_ar_i18n_injected"
    if st.session_state.get(key):
        return
    st.session_state[key] = True

    st.components.v1.html(
        """
        <script>
        (function(){
          const map = new Map([
            ["Choose an option", "اختر خيارًا"],
            ["Search", "بحث"],
            ["No options to select.", "لا توجد خيارات"],
            ["No options to select", "لا توجد خيارات"],
            ["Type to search", "اكتب للبحث"],
            ["Select an option", "اختر خيارًا"],
            ["Clear value", "مسح"],
          ]);

          function replaceText(node){
            if(!node) return;
            const walker = document.createTreeWalker(node, NodeFilter.SHOW_TEXT, null, false);
            let n;
            while(n = walker.nextNode()){
              const t = (n.nodeValue || "").trim();
              if(map.has(t)){
                n.nodeValue = n.nodeValue.replace(t, map.get(t));
              }
            }
          }

          function run(){
            replaceText(document.body);
          }

          run();
          const obs = new MutationObserver(()=>run());
          obs.observe(document.body, {subtree:true, childList:true, characterData:true});
        })();
        </script>
        """,
        height=0,
    )


def ar_selectbox(label, options, *, placeholder="اختر...", **kwargs):
    """
    Wrapper لـ st.selectbox مع placeholder عربي (إذا مدعوم في إصدار Streamlit).
    إذا placeholder غير مدعوم، ما يوقف التطبيق.
    """
    try:
        return st.selectbox(label, options, placeholder=placeholder, **kwargs)
    except TypeError:
        return st.selectbox(label, options, **kwargs)

def ar_multiselect(label, options, *, placeholder="ابحث أو اختر...", **kwargs):
    """
    Wrapper لـ st.multiselect مع placeholder عربي (إذا مدعوم).
    """
    try:
        return st.multiselect(label, options, placeholder=placeholder, **kwargs)
    except TypeError:
        return st.multiselect(label, options, **kwargs)

def ar_expander(label, *, expanded=False, icon=None):
    """
    Wrapper لـ st.expander (بس للتوحيد + إمكانية إضافة أيقونة في العنوان)
    """
    lab = f"{icon} {label}" if icon else label
    return st.expander(lab, expanded=expanded)


# ============================================================
# 🎨 Optional: Inject CSS styles once
# ============================================================



def inject_component_styles():
    """Backward-compatible helper.

    ✅ ملاحظة: معظم الستايلات الأساسية تُحقن الآن عبر styles.apply_custom_css().
    هذه الدالة تُترك كـ no-op لتفادي تكرار CSS أو ظهور <style> كنص داخل الواجهة.
    """
    return

# ============================================================
# 🧾 KPI Cards
# ============================================================

def render_kpi(label, value, color_class="neutral", icon="📊"):
    """
    نفس الدالة السابقة — تحسينات: أمان أكثر + هروب نصوص.
    """
    val_color = "#1E293B"
    if color_class == "success":
        val_color = "#059669"
    elif color_class == "danger":
        val_color = "#DC2626"
    elif color_class == "blue":
        val_color = "#2563EB"

    safe_label = html.escape(_safe_text(label))

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

def render_custom_table(
    df,
    columns_config=None,
    *,
    key=None,
    use_container_width: bool = True,
    height=None,
    **_kwargs,
):
    """
    columns_config يدعم شكلين:
    1) القديم: (col_key, label, col_type)
    2) الجديد: (col_key, label, col_type, format_func)
       format_func(val, row) -> (display_str, css_class)

    col_type المدعومة:
      - money / percent / colorful / badge / date
      - text / number / bool / auto / link
    """
    # NOTE:
    # - بعض الصفحات تستدعي هذه الدالة بنفس بارامترات Streamlit مثل (key/use_container_width/height).
    #   نحن نقبلها هنا حتى لا يتعطل التطبيق، لأنها لا تؤثر على HTML table الحالي.
    # - columns_config لو لم يُمرر سنحاول توليده تلقائياً من أعمدة الـ DataFrame.

    if df is None or df.empty:
        st.info("📭 لا توجد بيانات متاحة")
        return

    if columns_config is None:
        columns_config = [(c, c, "auto") for c in df.columns]

    html_out = '<div style="overflow-x:auto;"><table class="finance-table"><thead><tr>'

    for cfg in columns_config:
        label = cfg[1] if len(cfg) > 1 else ""
        html_out += f'<th>{html.escape(_safe_text(label))}</th>'
    html_out += "</tr></thead><tbody>"

    for _, row in df.iterrows():
        html_out += "<tr>"

        for cfg in columns_config:
            col_key = cfg[0]
            col_type = cfg[2] if len(cfg) > 2 else "auto"
            format_func = cfg[3] if len(cfg) > 3 else None

            val = row.get(col_key, "")

            # custom formatter
            if callable(format_func):
                try:
                    disp, cls = format_func(val, row)
                    # لو formatter رجّع HTML جاهز (مثل badge/link) لا نهربه
                    if isinstance(disp, str) and disp.strip().startswith("<"):
                        html_out += f'<td><span class="{html.escape(_safe_text(cls))}">{disp}</span></td>'
                    else:
                        html_out += f'<td><span class="{html.escape(_safe_text(cls))}">{html.escape(_safe_text(disp))}</span></td>'
                    continue
                except Exception:
                    pass

            display = _safe_text(val)
            cls = ""
            td_cls = ""

            if col_type == "money":
                x = _safe_number(val, default=None)
                display = _fmt_money(x) if x is not None else "-"
                cls = "txt-blue" if (x is not None and x > 0) else ""
                td_cls = "td-num"

            elif col_type == "percent":
                x = _safe_number(val, default=None)
                display = _fmt_percent(x) if x is not None else "-"
                cls = "txt-green" if (x is not None and x >= 0) else "txt-red"
                td_cls = "td-num"

            elif col_type == "colorful":
                x = _safe_number(val, default=None)
                display = _fmt_money(x) if x is not None else "-"
                cls = "txt-green" if (x is not None and x >= 0) else "txt-red"
                td_cls = "td-num"

            elif col_type == "number":
                x = _safe_number(val, default=None)
                display = f"{x:,.2f}" if x is not None else "-"
                td_cls = "td-num"

            elif col_type == "bool":
                s = str(val).strip().lower()
                truthy = s in ("1", "true", "yes", "y", "نعم", "صح") or val is True
                display = "✅" if truthy else "—"
                cls = "txt-green" if truthy else "txt-muted"

            elif col_type == "badge":
                s = str(val).lower()
                is_op = s.startswith("open") or s.startswith("مفتوح")
                badge_cls = "badge-open" if is_op else "badge-closed"
                badge_text = "مفتوحة" if is_op else "مغلقة"
                display = f'<span class="badge {badge_cls}">{badge_text}</span>'
                html_out += f"<td>{display}</td>"
                continue

            elif col_type == "date":
                display = _short_date(val)
                cls = "txt-muted"

            elif col_type == "link":
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

            elif col_type == "text":
                display = _safe_text(val)

            elif col_type == "auto":
                x = _safe_number(val, default=None)
                if x is not None:
                    display = f"{x:,.2f}"
                    td_cls = "td-num"
                else:
                    display = _short_date(val)

            else:
                display = _safe_text(val)

            # Escape exactly once unless it's an HTML snippet
            if isinstance(display, str) and display.strip().startswith("<"):
                escaped_display = display
            else:
                escaped_display = html.escape(_safe_text(display))

            html_out += f'<td class="{html.escape(td_cls)}"><span class="{html.escape(cls)}">{escaped_display}</span></td>'

        html_out += "</tr>"

    html_out += "</tbody></table></div>"
    st.markdown(html_out, unsafe_allow_html=True)


# ============================================================
# ✅ Smart Table Layer (Auto Columns + Search/Filter + Sort)
# ============================================================

def _guess_col_type(col_name: str, sample_val: Any = None) -> str:
    n = (col_name or "").strip().lower()

    # status/badge
    if n in ("status", "status_ar") or "status" in n or "الحالة" in n:
        return "badge"

    # date
    if "date" in n or "time" in n or n == "ts" or "تاريخ" in n:
        return "date"

    # percent
    if "pct" in n or "percent" in n or "نسبة" in n or n.endswith("%"):
        return "percent"
    if isinstance(sample_val, str) and "%" in sample_val:
        return "percent"

    # money-ish
    money_keys = (
        "price", "cost", "value", "amount", "cash", "revenue", "income",
        "assets", "liab", "equity", "debt",
        "سعر", "قيمة", "تكلفة", "مبلغ", "سيولة", "إيراد", "دخل",
        "أصول", "مطلوبات", "حقوق", "دين"
    )
    if any(k in n for k in money_keys):
        return "money"

    # qty
    if "qty" in n or "quantity" in n or "shares" in n or "كمية" in n:
        return "number"

    # gains/returns -> colorful
    gain_keys = ("gain", "pl", "profit", "loss", "return", "change", "growth", "عائد", "ربح", "خسارة", "تغير", "نمو")
    if any(k in n for k in gain_keys):
        return "colorful"

    # default: numeric?
    x = _safe_number(sample_val, default=None)
    if x is not None:
        return "number"

    return "text"


def _auto_label(col: str) -> str:
    """تحسين أسماء الأعمدة لو ما عندك mapping"""
    s = (col or "").strip()
    s = s.replace("_", " ")
    return s


def auto_columns_config(
    df: pd.DataFrame,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    rename_map: Optional[Dict[str, str]] = None,
    type_overrides: Optional[Dict[str, str]] = None,
    max_cols: int = 18,
) -> List[Tuple]:
    """
    يبني columns_config تلقائيًا لـ render_custom_table.
    """
    if df is None or df.empty:
        return []

    cols = list(df.columns)

    if include:
        cols = [c for c in include if c in df.columns]

    if exclude:
        ex = set(exclude)
        cols = [c for c in cols if c not in ex]

    cols = cols[:max_cols]

    cfg: List[Tuple] = []
    for c in cols:
        sample = None
        try:
            series = df[c]
            sample = series.dropna().iloc[0] if series is not None and series.notna().any() else None
        except Exception:
            sample = None

        if type_overrides and c in type_overrides:
            ctype = type_overrides[c]
        else:
            ctype = _guess_col_type(str(c), sample)

        label = (rename_map or {}).get(c, _auto_label(str(c)))
        cfg.append((c, label, ctype))

    return cfg


def _apply_search(df: pd.DataFrame, q: str, cols: Optional[List[str]] = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    q = (q or "").strip()
    if not q:
        return df

    cols = cols or list(df.columns)
    cols = [c for c in cols if c in df.columns]

    mask = pd.Series([False] * len(df), index=df.index)
    for c in cols:
        try:
            mask = mask | df[c].astype(str).str.contains(q, case=False, na=False)
        except Exception:
            pass
    return df[mask].copy()


def _apply_filters(df: pd.DataFrame, filters: Dict[str, List[str]]) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    out = df.copy()
    for col, selected in (filters or {}).items():
        if not selected or col not in out.columns:
            continue
        try:
            out = out[out[col].astype(str).isin([str(x) for x in selected])]
        except Exception:
            pass
    return out


def _apply_sort(df: pd.DataFrame, sort_col: Optional[str], ascending: bool) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    if not sort_col or sort_col not in df.columns:
        return df
    try:
        return df.sort_values(sort_col, ascending=ascending)
    except Exception:
        return df


def render_smart_table(
    df: pd.DataFrame,
    *,
    key: str,
    title: Optional[str] = None,
    columns_config: Optional[List[Tuple]] = None,
    include: Optional[List[str]] = None,
    exclude: Optional[List[str]] = None,
    rename_map: Optional[Dict[str, str]] = None,
    type_overrides: Optional[Dict[str, str]] = None,
    enable_search: bool = True,
    search_cols: Optional[List[str]] = None,
    filter_cols: Optional[List[str]] = None,
    enable_sort: bool = True,
    default_sort_col: Optional[str] = None,
    default_sort_asc: bool = False,
    max_rows: int = 500,
):
    """
    واجهة جاهزة:
    - توليد columns_config تلقائيًا (إن لم يُمرّر)
    - بحث + فلاتر + فرز
    """
    if df is None or df.empty:
        st.info("📭 لا توجد بيانات متاحة")
        return

    view_df = df.copy()
    if max_rows and len(view_df) > max_rows:
        view_df = view_df.head(max_rows).copy()

    if title:
        st.markdown(f"### {title}")

    q = ""
    filters: Dict[str, List[str]] = {}
    sort_col = None
    asc = default_sort_asc

    # Toolbar
    if enable_search or enable_sort:
        c1, c2, c3 = st.columns([2, 1, 1])

        with c1:
            if enable_search:
                q = st.text_input("🔎 بحث داخل الجدول", key=f"{key}_q")

        with c2:
            if enable_sort:
                sort_options = [c for c in view_df.columns]
                if default_sort_col and default_sort_col in sort_options:
                    idx = sort_options.index(default_sort_col)
                else:
                    idx = 0
                sort_col = st.selectbox("↕️ فرز حسب", sort_options, index=idx, key=f"{key}_sort_col")

        with c3:
            if enable_sort:
                asc = (st.selectbox("الاتجاه", ["⬇️ تنازلي", "⬆️ تصاعدي"],
                                    index=(1 if default_sort_asc else 0),
                                    key=f"{key}_sort_dir") == "⬆️ تصاعدي")

    # Filters
    if filter_cols:
        st.markdown("<div style='margin-top:6px;'></div>", unsafe_allow_html=True)
        fcols = st.columns(min(4, len(filter_cols)))
        for i, col in enumerate(filter_cols):
            if col not in view_df.columns:
                continue
            with fcols[i % len(fcols)]:
                try:
                    opts = sorted(view_df[col].astype(str).fillna("").unique().tolist())
                except Exception:
                    opts = []
                sel = st.multiselect(f"فلترة: {col}", opts, default=[], key=f"{key}_flt_{col}")
                if sel:
                    filters[col] = sel

    out = view_df
    if enable_search:
        out = _apply_search(out, q, cols=search_cols)
    out = _apply_filters(out, filters)
    if enable_sort:
        out = _apply_sort(out, sort_col, asc)

    cfg = columns_config or auto_columns_config(
        out,
        include=include,
        exclude=exclude,
        rename_map=rename_map,
        type_overrides=type_overrides,
    )

    render_custom_table(out, cfg)


# ============================================================
# 🧠 Osoli Report Renderer (Cards + Chips) ✅ NEW
# ============================================================

def _mi(symbol_name: str) -> str:
    """Material Symbol (Rounded) span"""
    return f'<span class="mi material-symbols-rounded">{html.escape(symbol_name)}</span>'

def render_osoli_report(report: Dict[str, Any], *, title: str = "📌 تقرير التحليل"):
    """
    يعرض dict تقرير التحليل بشكل بطاقات وchips.
    - لا يفترض شكل صارم للتقرير، ويحاول يقرأ مفاتيح شائعة.
    - أي شيء ما قدر يفهمه يتركه بدون كسر.
    """
    if not isinstance(report, dict) or not report:
        st.info("لا يوجد تقرير لعرضه.")
        return

    # مفاتيح شائعة (مرنة)
    score = report.get("osoli_score") or report.get("score") or report.get("OsoliScore")
    confidence = report.get("confidence") or report.get("conf") or report.get("confidence_pct")
    recommendation = report.get("recommendation") or report.get("signal") or report.get("action")

    gates = report.get("risk_gates") or report.get("gates") or report.get("risk") or {}
    evidence = report.get("evidence") or report.get("why") or report.get("signals") or []
    scenarios = report.get("scenarios") or report.get("scenario") or report.get("plans") or []

    # Header
    st.markdown(f"### {html.escape(_safe_text(title))}")

    # Chips row (Top summary)
    chips: List[str] = []

    if score is not None:
        try:
            s = _safe_number(score, default=None)
            score_txt = f"{s:.0f}/100" if s is not None else _safe_text(score)
        except Exception:
            score_txt = _safe_text(score)

        chip_cls = "os-chip-blue"
        try:
            s2 = _safe_number(score, default=None)
            if s2 is not None:
                chip_cls = "os-chip-green" if s2 >= 70 else ("os-chip-amber" if s2 >= 50 else "os-chip-red")
        except Exception:
            pass

        chips.append(
            f'<span class="os-chip {chip_cls}">{_mi("donut_large")} الدرجة: {html.escape(score_txt)}</span>'
        )

    if confidence is not None:
        conf_txt = _safe_text(confidence)
        chips.append(
            f'<span class="os-chip os-chip-gray">{_mi("verified")} الثقة: {html.escape(conf_txt)}</span>'
        )

    if recommendation:
        rec_txt = _safe_text(recommendation)
        chips.append(
            f'<span class="os-chip os-chip-blue">{_mi("tips_and_updates")} التوصية: {html.escape(rec_txt)}</span>'
        )

    if chips:
        st.markdown("".join(chips), unsafe_allow_html=True)

    # Cards grid
    st.markdown('<div class="os-grid">', unsafe_allow_html=True)

    # Card: Risk gates
    if isinstance(gates, dict) and gates:
        items = []
        for k, v in list(gates.items())[:12]:
            items.append(
                f'<div class="os-kv">'
                f'  <div class="os-k">{html.escape(_safe_text(k))}</div>'
                f'  <div class="os-v">{html.escape(_safe_text(v))}</div>'
                f'</div>'
            )

        st.markdown(
            f"""
            <div class="os-card os-col-6">
              <div class="os-card-title">{_mi("shield")} بوابات المخاطرة</div>
              {''.join(items)}
            </div>
            """,
            unsafe_allow_html=True
        )

    # Card: Evidence
    if isinstance(evidence, (list, tuple)) and evidence:
        bullets = []
        for x in list(evidence)[:14]:
            bullets.append(f"<li>{html.escape(_safe_text(x))}</li>")

        st.markdown(
            f"""
            <div class="os-card os-col-6">
              <div class="os-card-title">{_mi("fact_check")} الأدلة</div>
              <ul style="margin:0; padding-right:18px; color:#0F172A; font-weight:800;">
                {''.join(bullets)}
              </ul>
            </div>
            """,
            unsafe_allow_html=True
        )

    # Card: Scenarios
    if isinstance(scenarios, (list, tuple)) and scenarios:
        parts = []
        for sc in list(scenarios)[:8]:
            if isinstance(sc, dict):
                name = sc.get("name") or sc.get("title") or "سيناريو"
                entry = sc.get("entry") or sc.get("buy") or sc.get("trigger") or "-"
                stop = sc.get("stop") or sc.get("sl") or "-"
                tp = sc.get("targets") or sc.get("tp") or sc.get("take_profit") or "-"
                rr = sc.get("rr") or sc.get("r_r") or ""
                rr_txt = f" | R:R {rr}" if rr else ""

                parts.append(
                    f"""
                    <div style="border:1px solid rgba(15,23,42,0.10); border-radius:14px; padding:10px; margin-top:10px; background:#fff;">
                      <div style="font-weight:950;">{html.escape(_safe_text(name))}{html.escape(rr_txt)}</div>
                      <div class="os-muted">
                        دخول: <b style="color:#0F172A">{html.escape(_safe_text(entry))}</b>
                        — وقف: <b style="color:#DC2626">{html.escape(_safe_text(stop))}</b>
                        — أهداف: <b style="color:#059669">{html.escape(_safe_text(tp))}</b>
                      </div>
                    </div>
                    """
                )
            else:
                parts.append(
                    f"""
                    <div style="border:1px solid rgba(15,23,42,0.10); border-radius:14px; padding:10px; margin-top:10px; background:#fff;">
                      <div style="font-weight:900;">{html.escape(_safe_text(sc))}</div>
                    </div>
                    """
                )

        st.markdown(
            f"""
            <div class="os-card os-col-12">
              <div class="os-card-title">{_mi("route")} السيناريوهات</div>
              {''.join(parts)}
            </div>
            """,
            unsafe_allow_html=True
        )

    st.markdown("</div>", unsafe_allow_html=True)  # end grid
