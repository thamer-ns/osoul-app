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

          // run now + observe changes
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
        # إصدارات قديمة ما تدعم placeholder
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

def render_custom_table(df, columns_config):
    """
   # ============================================================
# ✅ Smart Table Layer (Auto Columns + Search/Filter + Smart Colors)
# ============================================================

def _guess_col_type(col_name: str, sample_val=None) -> str:
    n = (col_name or "").strip().lower()

    # status/badge
    if n in ("status", "status_ar") or "status" in n or "الحالة" in n:
        return "badge"

    # date
    if "date" in n or "time" in n or "ts" in n or "تاريخ" in n:
        return "date"

    # percent
    if "pct" in n or "percent" in n or "نسبة" in n or n.endswith("%"):
        return "percent"
    if isinstance(sample_val, str) and "%" in sample_val:
        return "percent"

    # money-ish
    money_keys = ("price", "cost", "value", "amount", "cash", "revenue", "income", "assets", "liab", "equity", "debt",
                  "سعر", "قيمة", "تكلفة", "مبلغ", "سيولة", "إيراد", "ربح", "أصول", "مطلوبات", "حقوق", "دين")
    if any(k in n for k in money_keys):
        return "money"

    # qty
    if "qty" in n or "quantity" in n or "shares" in n or "كمية" in n:
        return "number"

    # gains/returns -> colorful
    gain_keys = ("gain", "pl", "profit", "loss", "return", "change", "growth", "عائد", "ربح", "خسارة", "تغير", "نمو")
    if any(k in n for k in gain_keys):
        # لو كان pct غالبًا تم التقاطه فوق
        return "colorful"

    # default
    # إذا رقم -> number/auto
    x = _safe_number(sample_val, default=None)
    if x is not None:
        return "number"

    return "text"


def _auto_label(col: str) -> str:
    """تحسين أسماء الأعمدة لو ما عندك mapping"""
    s = (col or "").strip()
    # لطّف snake_case
    s = s.replace("_", " ")
    return s


def auto_columns_config(
    df: pd.DataFrame,
    *,
    include: list | None = None,
    exclude: list | None = None,
    rename_map: dict | None = None,
    type_overrides: dict | None = None,
    max_cols: int = 18,
) -> list:
    """
    يبني columns_config تلقائيًا لـ render_custom_table.
    - include: قائمة أعمدة محددة (إن وجدت)
    - exclude: أعمدة تستبعد
    - rename_map: {col: "label"}
    - type_overrides: {col: "money"/"percent"/...}
    """
    if df is None or df.empty:
        return []

    cols = list(df.columns)

    if include:
        cols = [c for c in include if c in df.columns]

    if exclude:
        ex = set(exclude)
        cols = [c for c in cols if c not in ex]

    # لا نطوّل جدًا
    cols = cols[:max_cols]

    cfg = []
    for c in cols:
        sample = None
        try:
            sample = df[c].dropna().iloc[0] if c in df.columns and df[c].notna().any() else None
        except Exception:
            sample = None

        ctype = None
        if type_overrides and c in type_overrides:
            ctype = type_overrides[c]
        else:
            ctype = _guess_col_type(str(c), sample)

        label = (rename_map or {}).get(c, _auto_label(str(c)))
        cfg.append((c, label, ctype))

    return cfg


def _apply_search(df: pd.DataFrame, q: str, cols: list | None = None) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    q = (q or "").strip()
    if not q:
        return df

    cols = cols or list(df.columns)
    cols = [c for c in cols if c in df.columns]

    # search as string contains
    mask = pd.Series([False] * len(df), index=df.index)
    for c in cols:
        try:
            mask = mask | df[c].astype(str).str.contains(q, case=False, na=False)
        except Exception:
            pass
    return df[mask].copy()


def _apply_filters(df: pd.DataFrame, filters: dict) -> pd.DataFrame:
    """
    filters مثال:
    {
      "status": ["Open"],
      "sector": ["Banks","Energy"]
    }
    """
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


def _apply_sort(df: pd.DataFrame, sort_col: str, ascending: bool) -> pd.DataFrame:
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
    title: str | None = None,
    columns_config: list | None = None,
    include: list | None = None,
    exclude: list | None = None,
    rename_map: dict | None = None,
    type_overrides: dict | None = None,
    enable_search: bool = True,
    search_cols: list | None = None,
    filter_cols: list | None = None,
    enable_sort: bool = True,
    default_sort_col: str | None = None,
    default_sort_asc: bool = False,
    max_rows: int = 500,
):
    """
    واجهة جاهزة:
    - توليد columns_config تلقائيًا (إن لم يُمرّر)
    - بحث + فلاتر + فرز
    - تلوين ذكي يعتمد على render_custom_table
    """
    if df is None or df.empty:
        st.info("📭 لا توجد بيانات متاحة")
        return

    # قص عدد الصفوف للواجهة (اختياري)
    view_df = df.copy()
    if max_rows and len(view_df) > max_rows:
        view_df = view_df.head(max_rows).copy()

    if title:
        st.markdown(f"### {title}")

    # ---- Toolbar
    q = ""
    filters = {}

    # row 1: search + sort
    if enable_search or enable_sort:
        c1, c2, c3 = st.columns([2, 1, 1])
        with c1:
            if enable_search:
                q = st.text_input("🔎 بحث داخل الجدول", key=f"{key}_q")
        with c2:
            sort_col = None
            if enable_sort:
                sort_options = [c for c in view_df.columns]
                if default_sort_col and default_sort_col in view_df.columns:
                    sort_col = st.selectbox("↕️ فرز حسب", sort_options, index=sort_options.index(default_sort_col), key=f"{key}_sort_col")
                else:
                    sort_col = st.selectbox("↕️ فرز حسب", sort_options, index=0, key=f"{key}_sort_col")
            else:
                sort_col = None
        with c3:
            asc = default_sort_asc
            if enable_sort:
                asc = st.selectbox("الاتجاه", ["⬇️ تنازلي", "⬆️ تصاعدي"], index=(1 if default_sort_asc else 0), key=f"{key}_sort_dir") == "⬆️ تصاعدي"
    else:
        sort_col, asc = None, default_sort_asc

    # row 2: filters
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

    # Apply search/filters/sort
    out = view_df
    if enable_search:
        out = _apply_search(out, q, cols=search_cols)
    out = _apply_filters(out, filters)
    if enable_sort:
        out = _apply_sort(out, sort_col, asc)

    # auto columns config
    cfg = columns_config or auto_columns_config(
        out,
        include=include,
        exclude=exclude,
        rename_map=rename_map,
        type_overrides=type_overrides,
    )

    # Render
    render_custom_table(out, cfg)
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