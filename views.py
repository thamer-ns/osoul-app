# views.py ✅ النسخة الكاملة بعد التعديلات
# (توحيد شكل جداول المختبر + التحليل المالي مع جدول الاستثمار)
# + ✅ استخدام get_financial_statements (DB + Yahoo + fallback) بدل الاعتماد فقط على المخزن

import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import date

from config import DEFAULT_COLORS
from components import (
    render_kpi,
    render_custom_table,
    render_ticker_card,
    safe_fmt,
    inject_component_styles,
    inject_streamlit_ar_i18n,
)
from analytics import (
    calculate_portfolio_metrics,
    update_prices,
    generate_equity_curve,
    create_smart_backup,
)
from database import execute_query, fetch_table, db_healthcheck
from market_data import get_tasi_data, get_chart_history, fetch_batch_data
from data_source import get_company_details
from security import validate_trade_inputs


# ========================================================
# 🛡️ Fail-Safe Imports
# ========================================================

# 1) Charts
try:
    from charts import render_technical_chart
except Exception:
    def render_technical_chart(symbol):
        st.warning("⚠️ ملف charts.py مفقود أو به خطأ.")


# 2) Backtester (مع إظهار سبب الفشل داخل الواجهة)
bt_import_error = None
try:
    from backtester import run_backtest, list_strategies
except Exception as e:
    run_backtest = None
    list_strategies = lambda: []
    bt_import_error = repr(e)


# 3) Financial Analysis
try:
    from financial_analysis import (
        get_thesis, save_thesis,
        FinancialParser, save_financial_record,
        get_stored_financials_df, get_advanced_fundamental_ratios,
        sync_auto_yahoo, get_fundamental_ratios,
        get_financial_statements,  # ✅ NEW
    )
except Exception:
    def get_thesis(s): return None
    def save_thesis(s, t, tg, r): pass
    def get_stored_financials_df(s, p): return pd.DataFrame()
    def get_advanced_fundamental_ratios(s): return {}
    def get_financial_statements(s, p="Annual", refresh=False): return pd.DataFrame()  # ✅ NEW fallback
    class FinancialParser:
        def process_file_or_text(self, uploaded_file=None, text_input=None):
            return [], None, "FinancialParser غير متوفر"
    def save_financial_record(*args, **kwargs): return False
    def sync_auto_yahoo(s): return False, "Module Missing"
    def get_fundamental_ratios(s): return {}


# 4) Classical Analysis
try:
    from classical_analysis import render_classical_analysis
except Exception:
    def render_classical_analysis(s):
        st.warning("⚠️ ملف classical_analysis.py مفقود أو به خطأ.")


# 5) AI Engine (تشخيص كامل بدل الصمت)
import traceback
ai_import_error = None

try:
    from ai_engine import (
        generate_ai_report,
        calculate_portfolio_risk_score,
        run_stress_test,
        generate_rebalancing_suggestions,
        save_user_rule,
        load_user_rules,
    )
except Exception:
    ai_import_error = traceback.format_exc()

    def generate_ai_report(symbol, timeframe="1D"):
        return {"__error__": "AI Engine import failed", "__trace__": ai_import_error}

    def calculate_portfolio_risk_score(df, c): return 50
    def run_stress_test(v, df): return {"scenarios": [], "insight": ""}
    def generate_rebalancing_suggestions(df, c): return []

    def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
        return {"ok": False, "reason": "AI Engine missing", "trace": ai_import_error}

    def load_user_rules(enabled_only=True, max_rows=50):
        return []


# ========================================================
# Helpers
# ========================================================

def _ensure_ui_once():
    """حقن CSS + تعريب placeholders مرة واحدة فقط."""
    if st.session_state.get("_ui_injected_once"):
        return
    st.session_state["_ui_injected_once"] = True
    try:
        inject_component_styles()
    except Exception:
        pass
    try:
        inject_streamlit_ar_i18n(True)
    except Exception:
        pass


def _normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if not sym:
        return ""
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym


def _safe_status_series(df: pd.DataFrame) -> pd.Series:
    """يرجع status موحد lower/strip لتفادي Open/OPEN/Close/Closed..."""
    if df is None or df.empty or "status" not in df.columns:
        return pd.Series([], dtype=str)
    return df["status"].astype(str).str.strip().str.lower()


def _select_strategy_ui(key_prefix: str = "lab"):
    """
    يدعم list_strategies سواء رجعت:
    - ["Trend","Sniper"]
    - [("Trend","ترند"), ("Sniper","قناص")]
    - [{"key":"Trend","name":"ترند"}]
    ويرجع دائمًا قيمة strategy كنص (string) لتفادي خطأ tuple.title()
    """
    raw = list_strategies() or ["Trend", "Sniper"]

    # tuples/lists: (key, name)
    if raw and isinstance(raw[0], (tuple, list)):
        strat_map = {}
        for item in raw:
            if not item:
                continue
            k = str(item[0])
            label = str(item[1]) if len(item) > 1 else k
            strat_map[label] = k

        if not strat_map:
            return "Trend"

        label = st.selectbox(
            "اختر الاستراتيجية",
            list(strat_map.keys()),
            index=0,
            key=f"{key_prefix}_strat_label",
        )
        return strat_map[label]

    # dicts
    if raw and isinstance(raw[0], dict):
        strat_map = {}
        for d in raw:
            k = str(d.get("key") or d.get("id") or d.get("value") or "")
            label = str(d.get("name") or d.get("label") or k)
            if k:
                strat_map[label] = k
        if strat_map:
            label = st.selectbox(
                "اختر الاستراتيجية",
                list(strat_map.keys()),
                index=0,
                key=f"{key_prefix}_strat_label",
            )
            return strat_map[label]
        return "Trend"

    raw_str = [str(x) for x in raw] if raw else ["Trend", "Sniper"]
    return st.selectbox("اختر الاستراتيجية", raw_str, index=0, key=f"{key_prefix}_strat")


def _clean_symbols_list(values) -> list:
    """ينظف الرموز: يحذف الفارغ/NaN ويطبّع ويزيل التكرار"""
    out = []
    try:
        for x in (values or []):
            s = _normalize_symbol(str(x))
            if s and s != ".SR" and s.lower() != "nan":
                out.append(s)
    except Exception:
        pass
    return list(sorted(set(out)))


# ========================================================
# ✅ NEW: Table wrapper (نفس تصميم جدول الاستثمار)
# ========================================================

def _render_table_like_trades(df: pd.DataFrame, cols_spec=None, max_rows: int = 400):
    """
    يعرض جدول بنفس تصميم جدول الاستثمار (render_custom_table)
    - cols_spec: [("col","Label","type"), ...]
    - لو None: يسوي mapping تلقائي للأعمدة
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        st.info("📭 لا توجد بيانات لعرضها")
        return

    d = df.copy()
    if max_rows and len(d) > max_rows:
        d = d.head(max_rows)

    label_map = {
        # عام
        "date": "التاريخ",
        "ts": "التاريخ",
        "time": "التاريخ",
        "year": "السنة",
        "period": "الفترة",
        "symbol": "الرمز",

        # مالي
        "revenue": "الإيرادات",
        "net_income": "صافي الربح",
        "operating_cash_flow": "التدفق النقدي التشغيلي",
        "total_assets": "إجمالي الأصول",
        "total_liabilities": "إجمالي المطلوبات",
        "current_assets": "الأصول المتداولة",
        "current_liabilities": "المطلوبات المتداولة",
        "total_equity": "حقوق الملكية",
        "long_term_debt": "ديون طويلة",

        # أسعار
        "open": "الافتتاح",
        "high": "الأعلى",
        "low": "الأدنى",
        "close": "الإغلاق",
        "volume": "الحجم",

        # Backtest
        "portfolio_value": "قيمة المحفظة",
        "return_pct": "العائد %",
        "final_value": "القيمة النهائية",
    }

    def _guess_type(col: str) -> str:
        c = str(col).lower()
        if c in ("date", "ts") or "date" in c or "time" in c:
            return "date"
        if any(k in c for k in ["pct", "percent", "margin", "ratio", "yield", "growth"]):
            return "percent"
        if any(k in c for k in ["price", "value", "amount", "revenue", "income", "cash", "assets", "liab", "equity", "debt", "cost", "market"]):
            return "money"
        if any(k in c for k in ["qty", "quantity", "volume"]):
            return "number"
        return "text"

    if cols_spec is None:
        cols_spec = []
        for col in list(d.columns)[:30]:
            key = str(col)
            lbl = label_map.get(key.lower(), key)
            cols_spec.append((key, lbl, _guess_type(key)))

    render_custom_table(d, cols_spec)


# ========================================================
# 1) Navigation
# ========================================================

def render_navbar():
    buttons = [
        ("🏠 الرئيسية", "home"),
        ("⚡ مضاربة", "spec"),
        ("💎 استثمار", "invest"),
        ("💓 نبض", "pulse"),
        ("📜 صكوك", "sukuk"),
        ("🔍 تحليل", "analysis"),
        ("🧪 المختبر", "backtest"),
        ("💰 السيولة", "cash"),
        ("🔄 تحديث", "update"),
    ]

    st.markdown(
        """<style>
        div.stButton > button {width: 100%; border-radius: 8px;}
        </style>""",
        unsafe_allow_html=True
    )

    cols = st.columns(len(buttons) + 1)

    for i, (label, key) in enumerate(buttons):
        with cols[i]:
            type_btn = "primary" if st.session_state.get("page") == key else "secondary"
            if st.button(label, key=f"nav_{key}", type=type_btn):
                st.session_state.page = key
                st.rerun()

    with cols[-1]:
        with st.popover("👤 القائمة"):
            st.write(f"مرحباً {st.session_state.get('username','User')}")
            if st.button("➕ إضافة صفقة", key="menu_add_trade"):
                st.session_state.page = "add"
                st.rerun()
            if st.button("⚙️ إعدادات", key="menu_settings"):
                st.session_state.page = "settings"
                st.rerun()

            st.markdown("---")
            if st.button("🚪 خروج", key="menu_logout"):
                try:
                    from security import logout
                    logout()
                except Exception:
                    st.session_state.clear()
                    st.rerun()


# ========================================================
# 2) Dashboard
# ========================================================

def view_dashboard(fin):
    try:
        tp, tc = get_tasi_data()
    except Exception:
        tp, tc = 0, 0

    ar = "🔼" if tc >= 0 else "🔽"
    df = fin.get("all_trades", pd.DataFrame())

    total_assets = float(fin.get("market_val_open", 0)) + float(fin.get("cash", 0))
    cash_pct = (float(fin.get("cash", 0)) / total_assets * 100) if total_assets else 0

    risk_score = calculate_portfolio_risk_score(df, cash_pct)
    risk_color = "success" if risk_score < 40 else "danger" if risk_score > 70 else "neutral"
    risk_label = "منخفضة" if risk_score < 40 else "عالية" if risk_score > 70 else "متوسطة"

    c_tasi, c_risk = st.columns([3, 1])
    with c_tasi:
        st.markdown(
            f"""
            <div class="tasi-card">
                <div>
                    <div style="opacity:0.9;">المؤشر العام (TASI)</div>
                    <div style="font-size:2.5rem; font-weight:900;">{safe_fmt(tp)}</div>
                </div>
                <div style="background:rgba(255,255,255,0.2); padding:5px 15px; border-radius:10px; font-weight:bold; direction:ltr;">
                    {ar} {tc:.2f}%
                </div>
            </div>
            """,
            unsafe_allow_html=True
        )
    with c_risk:
        render_kpi(f"المخاطرة ({risk_label})", f"{risk_score}/100", risk_color, "🛡️")

    c1, c2, c3, c4 = st.columns(4)
    total_pl = float(fin.get("unrealized_pl", 0)) + float(fin.get("realized_pl", 0))
    with c1:
        render_kpi(f"الكاش ({cash_pct:.1f}%)", safe_fmt(fin.get("cash", 0)), "blue", "💵")
    with c2:
        render_kpi("صافي الإيداعات", safe_fmt(fin.get("total_deposited", 0) - fin.get("total_withdrawn", 0)), "neutral", "🏗️")
    with c3:
        render_kpi("إجمالي الأصول", safe_fmt(total_assets), "neutral", "🏦")
    with c4:
        render_kpi("صافي الربح الكلي", safe_fmt(total_pl), "success" if total_pl >= 0 else "danger", "📈")

    st.markdown("---")

    o1, o2, o3, o4 = st.columns(4)
    open_pct = (float(fin.get("unrealized_pl", 0)) / float(fin.get("cost_open", 0)) * 100) if float(fin.get("cost_open", 0)) else 0
    with o1: render_kpi("التكلفة", safe_fmt(fin.get("cost_open", 0)), "neutral")
    with o2: render_kpi("القيمة السوقية", safe_fmt(fin.get("market_val_open", 0)), "blue")
    with o3: render_kpi("الربح الورقي", safe_fmt(fin.get("unrealized_pl", 0)), "success" if float(fin.get("unrealized_pl", 0)) >= 0 else "danger")
    with o4: render_kpi("النمو", f"{open_pct:.2f}%", "success" if open_pct >= 0 else "danger")

    st.markdown("<div style='margin-bottom: 25px;'></div>", unsafe_allow_html=True)

    if not df.empty:
        status = _safe_status_series(df)
        closed_df = df[status.isin(["close", "closed"])].copy() if len(status) else pd.DataFrame()
        closed_cost = float(closed_df["total_cost"].sum()) if (not closed_df.empty and "total_cost" in closed_df.columns) else 0
        closed_sales = float(closed_df["market_value"].sum()) if (not closed_df.empty and "market_value" in closed_df.columns) else 0
        closed_pl = float(fin.get("realized_pl", 0))
        closed_pct = (closed_pl / closed_cost * 100) if closed_cost else 0.0
    else:
        closed_cost = closed_sales = closed_pl = closed_pct = 0

    st.markdown("##### 📜 ملخص الصفقات المنفذة (Executed)")
    x1, x2, x3, x4 = st.columns(4)
    with x1: render_kpi("رأس المال المسترد", safe_fmt(closed_cost), "neutral", "↩️")
    with x2: render_kpi("السيولة العائدة", safe_fmt(closed_sales), "blue", "📥")
    with x3: render_kpi("الربح المحقق", safe_fmt(closed_pl), "success" if closed_pl >= 0 else "danger", "✅")
    with x4: render_kpi("العائد المحقق", f"{closed_pct:.2f}%", "success" if closed_pct >= 0 else "danger", "٪")

    st.markdown("---")

    if not df.empty and "status" in df.columns:
        status = _safe_status_series(df)
        open_trades = df[status == "open"].copy()
        invest_val = 0
        spec_val = 0
        sukuk_val = 0

        try:
            if "strategy" in open_trades.columns and "market_value" in open_trades.columns:
                invest_val = open_trades[open_trades["strategy"].astype(str).str.contains("استثمار", na=False)]["market_value"].sum()
                spec_val = open_trades[open_trades["strategy"].astype(str).str.contains("مضاربة", na=False)]["market_value"].sum()
        except Exception:
            pass

        if "asset_type" in open_trades.columns and "market_value" in open_trades.columns:
            sukuk_val = open_trades[open_trades["asset_type"].astype(str).str.lower() == "sukuk"]["market_value"].sum()

        alloc_df = pd.DataFrame({
            "Asset": ["استثمار", "مضاربة", "صكوك", "كاش"],
            "Value": [invest_val, spec_val, sukuk_val, float(fin.get("cash", 0))]
        })
        alloc_df = alloc_df[alloc_df["Value"] > 0]

        c_ch1, c_ch2 = st.columns(2)
        with c_ch1:
            st.subheader("توزيع الأصول")
            if not alloc_df.empty:
                st.plotly_chart(px.pie(alloc_df, values="Value", names="Asset", hole=0.4), use_container_width=True)
            else:
                st.info("لا توجد أصول")
        with c_ch2:
            st.subheader("نمو المحفظة")
            crv = generate_equity_curve(df)
            if isinstance(crv, pd.DataFrame) and not crv.empty and "date" in crv.columns:
                ycol = "cumulative_invested" if "cumulative_invested" in crv.columns else crv.columns[-1]
                st.plotly_chart(px.line(crv, x="date", y=ycol), use_container_width=True)
            else:
                st.info("لا توجد بيانات تاريخية")
    else:
        st.info("👋 مرحباً بك! ابدأ بإضافة صفقات.")


# ========================================================
# 3) Portfolio View
# ========================================================

def view_portfolio(fin, key):
    ts = "مضاربة" if key == "spec" else "استثمار"
    st.header(f"💼 محفظة {ts}")

    st.markdown(
        """<style>
        .finance-table td, .finance-table th {
            white-space: nowrap !important;
            font-size: 0.85rem !important;
            vertical-align: middle !important;
        }
        </style>""",
        unsafe_allow_html=True
    )

    df = fin.get("all_trades", pd.DataFrame())
    if df.empty:
        sub = pd.DataFrame(columns=["status", "total_cost", "market_value", "gain", "symbol", "date", "id"])
    else:
        if "strategy" in df.columns:
            sub = df[df["strategy"].astype(str).str.contains(ts, na=False)].copy()
        else:
            sub = df.copy()

    status = _safe_status_series(sub) if not sub.empty else pd.Series([], dtype=str)
    if len(status):
        op = sub[status == "open"].copy()
        cl = sub[status.isin(["close", "closed"])].copy()
    else:
        op = sub.copy()
        cl = pd.DataFrame()

    t1, t2 = st.tabs(["الصفقات القائمة", "الأرشيف"])

    with t1:
        k1, k2, k3, k4 = st.columns(4)
        total_cost = float(op["total_cost"].sum()) if (not op.empty and "total_cost" in op.columns) else 0
        total_market = float(op["market_value"].sum()) if (not op.empty and "market_value" in op.columns) else 0
        total_gain = float(op["gain"].sum()) if (not op.empty and "gain" in op.columns) else 0
        total_pct = (total_gain / total_cost * 100) if total_cost else 0.0

        with k1: render_kpi("إجمالي التكلفة", safe_fmt(total_cost), "neutral")
        with k2: render_kpi("سعر السوق", safe_fmt(total_market), "blue")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")

        st.markdown("---")

        if not op.empty:
            for col in ["company_name", "sector", "gain_pct", "weight"]:
                if col not in op.columns:
                    op[col] = ""

            sort_opts = [
                "الربح (الأعلى)", "القيمة (الأعلى)", "التاريخ (الأحدث)", "الرمز", "الشركة", "القطاع",
                "الكمية", "التكلفة", "السعر الحالي", "نسبة الربح", "التغير اليومي"
            ]
            c_sort, _ = st.columns([1, 3])
            sort_by = c_sort.selectbox(f"فرز {ts} حسب:", sort_opts, key=f"s_op_{key}")

            # ✅ تنظيف الرموز قبل جلب الأسعار
            symbols = _clean_symbols_list(op["symbol"].astype(str).tolist()) if "symbol" in op.columns else []
            try:
                live_data = fetch_batch_data(symbols) if symbols else {}
            except Exception:
                live_data = {}

            # ✅ طبّع عمود symbol داخل الجدول (لمنع mismatch)
            if "symbol" in op.columns:
                op["symbol"] = op["symbol"].astype(str).apply(_normalize_symbol)

            op["current_price"] = op["symbol"].apply(lambda x: live_data.get(x, {}).get("price", 0))
            op["prev_close"] = op["symbol"].apply(lambda x: live_data.get(x, {}).get("prev_close", 0))

            op["day_change"] = op.apply(
                lambda r: ((r.get("current_price", 0) - r.get("prev_close", 0)) / r.get("prev_close", 1) * 100)
                if (r.get("prev_close", 0) and r.get("prev_close", 0) > 0) else 0,
                axis=1
            )
            op["status_ar"] = "مفتوحة"

            if "الربح" in sort_by and "gain" in op.columns:
                op = op.sort_values("gain", ascending=False)
            elif "القيمة" in sort_by and "market_value" in op.columns:
                op = op.sort_values("market_value", ascending=False)
            elif "الرمز" in sort_by and "symbol" in op.columns:
                op = op.sort_values("symbol")
            elif "التغير اليومي" in sort_by and "day_change" in op.columns:
                op = op.sort_values("day_change", ascending=False)
            elif "نسبة الربح" in sort_by and "gain_pct" in op.columns:
                op = op.sort_values("gain_pct", ascending=False)
            elif "الشركة" in sort_by and "company_name" in op.columns:
                op = op.sort_values("company_name")
            elif "القطاع" in sort_by and "sector" in op.columns:
                op = op.sort_values("sector")
            elif "التكلفة" in sort_by and "total_cost" in op.columns:
                op = op.sort_values("total_cost", ascending=False)
            else:
                if "date" in op.columns:
                    op = op.sort_values("date", ascending=False)

            render_custom_table(
                op,
                [
                    ("company_name", "اسم الشركة", "text"),
                    ("sector", "القطاع", "text"),
                    ("status_ar", "الحالة", "badge"),
                    ("symbol", "رمز الشركة", "text"),
                    ("date", "تاريخ الشراء", "date"),
                    ("quantity", "الكمية", "money"),
                    ("entry_price", "سعر الشراء", "money"),
                    ("total_cost", "التكلفة", "money"),
                    ("current_price", "السعر الحالي", "money"),
                    ("market_value", "سعر السوق", "money"),
                    ("gain", "الربح والخسارة", "colorful"),
                    ("gain_pct", "نسبة الربح والخسارة", "percent"),
                    ("weight", "وزن السهم", "percent"),
                    ("day_change", "نسبة التغير اليومي", "percent"),
                ]
            )

            c_a1, c_a2 = st.columns(2)

            with c_a1:
                with st.expander("🔴 تسجيل بيع / إغلاق"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        s_id = st.selectbox(
                            "اختر الصفقة",
                            op["id"].tolist(),
                            format_func=lambda x: f"{op[op['id']==x]['company_name'].iloc[0]} ({op[op['id']==x]['symbol'].iloc[0]})",
                            key=f"sell_{key}"
                        )
                        if s_id:
                            with st.form(f"frm_sell_{key}_{s_id}"):
                                pr = st.number_input("سعر البيع", min_value=0.0, step=0.01, key=f"sell_price_{key}_{s_id}")
                                dt = st.date_input("تاريخ البيع", date.today(), key=f"sell_date_{key}_{s_id}")
                                if st.form_submit_button("تأكيد"):
                                    valid, msg = validate_trade_inputs(1, pr)
                                    if valid:
                                        execute_query(
                                            "UPDATE trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s",
                                            (pr, str(dt), s_id)
                                        )
                                        st.success("تم البيع")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    else:
                        st.info("لا توجد صفقات لاختيارها")

            with c_a2:
                with st.expander("✏️ تعديل صفقة (تصحيح خطأ)"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        e_id = st.selectbox("اختر الصفقة", op["id"].tolist(), key=f"edit_{key}")
                        if e_id:
                            rw = op[op["id"] == e_id].iloc[0]
                            with st.form(f"frm_edit_{key}_{e_id}"):
                                nq = st.number_input("الكمية", value=float(rw.get("quantity", 1)), min_value=1.0, key=f"edit_q_{key}_{e_id}")
                                np_ = st.number_input("سعر الشراء", value=float(rw.get("entry_price", 0)), min_value=0.0, key=f"edit_p_{key}_{e_id}")
                                try:
                                    nd_val = pd.to_datetime(rw.get("date", date.today())).date()
                                except Exception:
                                    nd_val = date.today()
                                nd = st.date_input("تاريخ الشراء", nd_val, key=f"edit_d_{key}_{e_id}")
                                if st.form_submit_button("حفظ"):
                                    valid, msg = validate_trade_inputs(nq, np_)
                                    if valid:
                                        execute_query(
                                            "UPDATE trades SET quantity=%s, entry_price=%s, date=%s WHERE id=%s",
                                            (nq, np_, str(nd), e_id)
                                        )
                                        st.success("تم التعديل")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    else:
                        st.info("لا توجد صفقات لاختيارها")
        else:
            st.info("لا توجد صفقات قائمة حالياً")

        st.markdown("---")
        if st.button("➕ إضافة سهم", key=f"add_{key}", type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with t2:
        if not cl.empty:
            sort_cl = st.selectbox(
                "فرز الأرشيف:",
                ["التاريخ (الأحدث)", "الربح (الأعلى)", "قيمة البيع (الأعلى)"],
                key=f"s_cl_{key}"
            )
            if "الربح" in sort_cl and "gain" in cl.columns:
                cl = cl.sort_values("gain", ascending=False)
            elif "قيمة البيع" in sort_cl and "market_value" in cl.columns:
                cl = cl.sort_values("market_value", ascending=False)
            else:
                if "exit_date" in cl.columns:
                    cl = cl.sort_values("exit_date", ascending=False)

            render_custom_table(
                cl,
                [
                    ("company_name", "الشركة", "text"),
                    ("symbol", "الرمز", "text"),
                    ("gain", "الربح", "colorful"),
                    ("gain_pct", "%", "percent"),
                    ("exit_date", "تاريخ البيع", "date"),
                ]
            )
        else:
            st.info("الأرشيف فارغ")


# ========================================================
# 4) Sukuk Portfolio
# ========================================================

def view_sukuk_portfolio(fin):
    st.header("📜 محفظة الصكوك")
    df = fin.get("all_trades", pd.DataFrame())

    if df.empty or "asset_type" not in df.columns:
        sukuk = pd.DataFrame()
    else:
        sukuk = df[df["asset_type"].astype(str).str.lower() == "sukuk"].copy()

    status = _safe_status_series(sukuk) if not sukuk.empty else pd.Series([], dtype=str)
    if len(status):
        op = sukuk[status == "open"].copy()
        cl = sukuk[status.isin(["close", "closed"])].copy()
    else:
        op = sukuk.copy()
        cl = pd.DataFrame()

    t1, t2 = st.tabs(["الصكوك القائمة (Open)", "الأرشيف (Closed)"])

    with t1:
        total_cost = float(op["total_cost"].sum()) if (not op.empty and "total_cost" in op.columns) else 0
        total_market = float(op["market_value"].sum()) if (not op.empty and "market_value" in op.columns) else 0
        total_gain = float(op["gain"].sum()) if (not op.empty and "gain" in op.columns) else 0
        total_pct = (total_gain / total_cost * 100) if total_cost else 0.0

        k1, k2, k3, k4 = st.columns(4)
        with k1: render_kpi("إجمالي الاستثمار", safe_fmt(total_cost), "neutral", "🕌")
        with k2: render_kpi("القيمة الحالية", safe_fmt(total_market), "blue", "📊")
        with k3: render_kpi("الربح/الخسارة", safe_fmt(total_gain), "success" if total_gain >= 0 else "danger", "📈")
        with k4: render_kpi("النسبة %", f"{total_pct:.2f}%", "success" if total_pct >= 0 else "danger", "٪")

        st.markdown("---")

        if not op.empty:
            if "company_name" not in op.columns:
                op["company_name"] = op.get("symbol", "")
            op["company_name"] = op["company_name"].fillna(op.get("symbol", ""))

            if "date" in op.columns:
                op["months_held"] = ((pd.to_datetime(date.today()) - pd.to_datetime(op["date"])).dt.days / 30).astype(int)
            else:
                op["months_held"] = 0

            if "entry_price" in op.columns:
                op["current_price"] = op["entry_price"]
            else:
                op["current_price"] = 0

            sb = st.selectbox("فرز الصكوك حسب:", ["التاريخ (الأحدث)", "القيمة (الأعلى)", "الاسم"], key="sort_sk")
            if "القيمة" in sb and "total_cost" in op.columns:
                op = op.sort_values("total_cost", ascending=False)
            elif "الاسم" in sb and "company_name" in op.columns:
                op = op.sort_values("company_name")
            else:
                if "date" in op.columns:
                    op = op.sort_values("date", ascending=False)

            render_custom_table(
                op,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("quantity", "العدد", "text"),
                    ("entry_price", "التكلفة (للوحدة)", "money"),
                    ("current_price", "السعر الحالي", "money"),
                    ("total_cost", "الاجمالي", "money"),
                    ("months_held", "المده (شهر)", "text"),
                ]
            )

            c1, c2 = st.columns(2)

            with c1:
                with st.expander("💰 بيع / تصفية صك"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        sid = st.selectbox(
                            "اختر الصك للبيع:",
                            op["id"].tolist(),
                            format_func=lambda x: f"{op[op['id']==x]['company_name'].iloc[0]}",
                            key="sell_sukuk_sel"
                        )
                        if sid:
                            curr_sell = op[op["id"] == sid].iloc[0]
                            with st.form(f"sk_sell_{sid}"):
                                st.write(f"تصفية: **{curr_sell.get('company_name','-')}**")
                                val = st.number_input("المبلغ المستلم كاملاً", min_value=0.0, step=100.0, key=f"sk_val_{sid}")
                                dt = st.date_input("تاريخ البيع", date.today(), key=f"sk_dt_{sid}")
                                if st.form_submit_button("تأكيد البيع"):
                                    qty = float(curr_sell.get("quantity", 0) or 0)
                                    if qty > 0:
                                        ep = val / qty
                                        execute_query(
                                            "UPDATE trades SET status='Close', exit_price=%s, exit_date=%s WHERE id=%s",
                                            (ep, str(dt), sid)
                                        )
                                        st.success("تم الحفظ")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error("خطأ: الكمية صفر")
                    else:
                        st.info("لا توجد صكوك لاختيارها")

            with c2:
                with st.expander("✏️ تعديل بيانات صك"):
                    if "id" in op.columns and len(op["id"].tolist()) > 0:
                        eid = st.selectbox("اختر الصك للتعديل:", op["id"].tolist(), key="sk_e")
                        if eid:
                            rw = op[op["id"] == eid].iloc[0]
                            with st.form(f"sk_edit_{eid}"):
                                nm = st.text_input("اسم الصك", value=str(rw.get("company_name", "")), key=f"sk_nm_{eid}")
                                qt = st.number_input("عدد الصكوك", value=float(rw.get("quantity", 1)), min_value=1.0, key=f"sk_qt_{eid}")
                                pr = st.number_input("قيمة الصك", value=float(rw.get("entry_price", 0)), min_value=0.0, key=f"sk_pr_{eid}")
                                try:
                                    nd_val = pd.to_datetime(rw.get("date", date.today())).date()
                                except Exception:
                                    nd_val = date.today()
                                nd = st.date_input("تاريخ الشراء", nd_val, key=f"sk_nd_{eid}")
                                if st.form_submit_button("حفظ التصحيح"):
                                    valid, msg = validate_trade_inputs(qt, pr)
                                    if valid:
                                        execute_query(
                                            "UPDATE trades SET symbol=%s, company_name=%s, quantity=%s, entry_price=%s, date=%s WHERE id=%s",
                                            (nm, nm, qt, pr, str(nd), eid)
                                        )
                                        st.success("تم التعديل")
                                        st.cache_data.clear()
                                        st.rerun()
                                    else:
                                        st.error(msg)
                    else:
                        st.info("لا توجد صكوك لاختيارها")
        else:
            st.info("لا توجد صكوك قائمة حالياً")

        st.markdown("---")
        if st.button("➕ إضافة صك", key="add_sukuk_btn", type="primary"):
            st.session_state.page = "add"
            st.rerun()

    with t2:
        if not cl.empty:
            if "company_name" not in cl.columns:
                cl["company_name"] = cl.get("symbol", "")
            cl["company_name"] = cl["company_name"].fillna(cl.get("symbol", ""))

            if "market_value" in cl.columns and "total_cost" in cl.columns:
                cl["realized_return"] = cl["market_value"] - cl["total_cost"]
            else:
                cl["realized_return"] = 0

            sort_by_cl = st.selectbox("فرز الأرشيف حسب:", ["تاريخ البيع (الأحدث)", "الربح (الأعلى)"], key="sort_sukuk_cl")
            if "الربح" in sort_by_cl and "realized_return" in cl.columns:
                cl = cl.sort_values("realized_return", ascending=False)
            else:
                if "exit_date" in cl.columns:
                    cl = cl.sort_values("exit_date", ascending=False)

            render_custom_table(
                cl,
                [
                    ("company_name", "اسم الصك", "text"),
                    ("total_cost", "التكلفة", "money"),
                    ("market_value", "قيمة البيع", "money"),
                    ("realized_return", "الربح المحقق", "colorful"),
                    ("exit_date", "تاريخ البيع", "date"),
                ]
            )
        else:
            st.info("أرشيف الصكوك فارغ")


# ========================================================
# 5) Cash Log
# ========================================================

def view_cash_log(fin):
    st.header("💰 السيولة والسجلات المالية")

    dep = fin.get("deposits", pd.DataFrame())
    wit = fin.get("withdrawals", pd.DataFrame())
    ret = fin.get("returns", pd.DataFrame())

    c1, c2, c3 = st.columns(3)
    with c1: render_kpi("إجمالي الإيداعات", safe_fmt(dep["amount"].sum() if (not dep.empty and "amount" in dep.columns) else 0), "success", "📥")
    with c2: render_kpi("إجمالي السحوبات", safe_fmt(wit["amount"].sum() if (not wit.empty and "amount" in wit.columns) else 0), "danger", "📤")
    with c3: render_kpi("إجمالي العوائد", safe_fmt(ret["amount"].sum() if (not ret.empty and "amount" in ret.columns) else 0), "blue", "🎁")

    st.markdown("---")
    t1, t2, t3 = st.tabs(["📥 سجل الإيداعات", "📤 سجل السحوبات", "🎁 سجل العوائد"])
    cols_base = [("date", "التاريخ", "date"), ("amount", "المبلغ", "money"), ("note", "ملاحظات", "text")]

    with t1:
        with st.expander("➕ تسجيل إيداع جديد"):
            with st.form("new_dep"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0, key="dep_amt")
                d = st.date_input("التاريخ", date.today(), key="dep_date")
                n = st.text_input("ملاحظة", key="dep_note")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        execute_query("INSERT INTO deposits (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not dep.empty:
            render_custom_table(dep.sort_values("date", ascending=False) if "date" in dep.columns else dep, cols_base)
            st.markdown("---")
            with st.expander("✏️ تعديل سجل إيداع سابق"):
                if "id" in dep.columns:
                    dep_map = {f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"] for _, row in dep.iterrows()}
                    sel_dep = st.selectbox("اختر العملية للتعديل:", list(dep_map.keys()), key="edit_dep_sel")
                    if sel_dep:
                        tid = dep_map[sel_dep]
                        curr = dep[dep["id"] == tid].iloc[0]
                        with st.form(f"edit_dep_form_{tid}"):
                            na = st.number_input("المبلغ الصحيح", value=float(curr.get("amount", 0)), key=f"dep_fix_amt_{tid}")
                            nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr.get("date", date.today())).date(), key=f"dep_fix_date_{tid}")
                            nn = st.text_input("ملاحظة", value=str(curr.get("note", "") or ""), key=f"dep_fix_note_{tid}")
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query("UPDATE deposits SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                                st.success("تم التعديل بنجاح")
                                st.cache_data.clear()
                                st.rerun()

    with t2:
        with st.expander("➖ تسجيل سحب جديد"):
            with st.form("new_wit"):
                a = st.number_input("المبلغ", min_value=0.0, step=100.0, key="wit_amt")
                d = st.date_input("التاريخ", date.today(), key="wit_date")
                n = st.text_input("ملاحظة", key="wit_note")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        execute_query("INSERT INTO withdrawals (date, amount, note) VALUES (%s,%s,%s)", (str(d), a, n))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not wit.empty:
            render_custom_table(wit.sort_values("date", ascending=False) if "date" in wit.columns else wit, cols_base)
            st.markdown("---")
            with st.expander("✏️ تعديل سجل سحب سابق"):
                if "id" in wit.columns:
                    wit_map = {f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"] for _, row in wit.iterrows()}
                    sel_wit = st.selectbox("اختر العملية للتعديل:", list(wit_map.keys()), key="edit_wit_sel")
                    if sel_wit:
                        tid = wit_map[sel_wit]
                        curr = wit[wit["id"] == tid].iloc[0]
                        with st.form(f"edit_wit_form_{tid}"):
                            na = st.number_input("المبلغ الصحيح", value=float(curr.get("amount", 0)), key=f"wit_fix_amt_{tid}")
                            nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr.get("date", date.today())).date(), key=f"wit_fix_date_{tid}")
                            nn = st.text_input("ملاحظة", value=str(curr.get("note", "") or ""), key=f"wit_fix_note_{tid}")
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query("UPDATE withdrawals SET amount=%s, date=%s, note=%s WHERE id=%s", (na, str(nd), nn, tid))
                                st.success("تم التعديل بنجاح")
                                st.cache_data.clear()
                                st.rerun()

    with t3:
        with st.expander("💵 تسجيل عائد/توزيع"):
            with st.form("new_ret"):
                s_raw = st.text_input("رمز السهم", key="ret_sym")
                a = st.number_input("المبلغ", min_value=0.0, step=10.0, key="ret_amt")
                d = st.date_input("التاريخ", date.today(), key="ret_date")
                if st.form_submit_button("حفظ"):
                    if a > 0:
                        s = _normalize_symbol(s_raw)
                        execute_query("INSERT INTO returnsgrants (date, symbol, amount) VALUES (%s,%s,%s)", (str(d), s, a))
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not ret.empty:
            render_custom_table(
                ret.sort_values("date", ascending=False) if "date" in ret.columns else ret,
                [("date", "التاريخ", "date"), ("symbol", "السهم", "text"), ("amount", "المبلغ", "money")]
            )
            st.markdown("---")
            with st.expander("✏️ تعديل سجل عائد سابق"):
                if "id" in ret.columns:
                    ret_map = {f"{row.get('date','-')} - {row.get('symbol','-')} - {row.get('amount','-')}": row["id"] for _, row in ret.iterrows()}
                    sel_ret = st.selectbox("اختر العملية للتعديل:", list(ret_map.keys()), key="edit_ret_sel")
                    if sel_ret:
                        tid = ret_map[sel_ret]
                        curr = ret[ret["id"] == tid].iloc[0]
                        with st.form(f"edit_ret_form_{tid}"):
                            ns_raw = st.text_input("رمز السهم", value=str(curr.get("symbol", "")), key=f"ret_fix_sym_{tid}")
                            na = st.number_input("المبلغ الصحيح", value=float(curr.get("amount", 0)), key=f"ret_fix_amt_{tid}")
                            nd = st.date_input("التاريخ الصحيح", pd.to_datetime(curr.get("date", date.today())).date(), key=f"ret_fix_date_{tid}")
                            if st.form_submit_button("حفظ التعديلات"):
                                ns = _normalize_symbol(ns_raw)
                                execute_query("UPDATE returnsgrants SET symbol=%s, amount=%s, date=%s WHERE id=%s", (ns, na, str(nd), tid))
                                st.success("تم التعديل")
                                st.cache_data.clear()
                                st.rerun()


# ========================================================
# 6) Financial UI
# ========================================================

def render_data_import_ui_content(symbol):
    st.info("يدعم النظام: ملفات PDF من تداول، ملفات Excel/CSV، أو النسخ واللصق المباشر.")
    parser = FinancialParser()

    uploaded_file = st.file_uploader("رفع ملف قوائم مالية (PDF, Excel, CSV)", type=["pdf", "xlsx", "xls", "csv"])
    pasted_text = st.text_area("أو الصق البيانات هنا مباشرة:")

    if st.button("🚀 معالجة واستخراج البيانات", key=f"fin_parse_{symbol}"):
        results, detected_symbol, err = [], None, None

        with st.spinner("جاري تحليل النصوص واستخراج الأرقام..."):
            if uploaded_file:
                results, detected_symbol, err = parser.process_file_or_text(uploaded_file=uploaded_file)
            elif pasted_text:
                results, detected_symbol, err = parser.process_file_or_text(text_input=pasted_text)
            else:
                st.warning("الرجاء اختيار ملف أو لصق نص.")
                return

        if err:
            st.error(err)
            return

        if results:
            st.success(f"تم استخراج {len(results)} سجلات بنجاح!")
            final_symbol = symbol

            if detected_symbol and detected_symbol != symbol:
                st.warning(f"⚠️ الملف لشركة {detected_symbol}، وأنت في صفحة {symbol}.")
                if st.checkbox(f"استخدام {detected_symbol}؟", value=True, key=f"use_detect_{symbol}"):
                    final_symbol = detected_symbol

            if not final_symbol:
                final_symbol = st.text_input("⚠️ الرجاء إدخال رمز السهم (مثال: 1120.SR):", key=f"fin_manual_sym_{symbol}")

            if final_symbol:
                st.write("### 🧐 مراجعة البيانات المستخرجة:")
                preview_df = pd.DataFrame([{"Date": r["date"], **r["data"]} for r in results])

                # ✅ بدل st.dataframe: نفس تصميم جدول الاستثمار
                _render_table_like_trades(preview_df, max_rows=200)

                if st.button("💾 تأكيد وحفظ في قاعدة البيانات", key=f"fin_save_{final_symbol}"):
                    count = 0
                    for r in results:
                        # ✅ FIX: لا تمرر source كموقع رابع (كان يروح period_type بالغلط)
                        if save_financial_record(final_symbol, r["date"], r["data"], period_type="Annual", source="File/Paste"):
                            count += 1
                    st.success(f"تم حفظ {count} سجلات لشركة {final_symbol}.")
                    st.rerun()
            else:
                st.error("يجب تحديد رمز السهم للحفظ.")
        else:
            st.error("لم يتم العثور على بيانات مالية صالحة.")


def render_financial_dashboard_ui(symbol):
    tab_dashboard, tab_data_mgmt = st.tabs(["📊 لوحة التحليل المالي", "⚙️ إدارة البيانات"])

    with tab_dashboard:
        # ✅ NEW: اجلب السنوي والربعي بطريقة موحّدة (DB + Yahoo + fallback)
        df_annual = get_financial_statements(symbol, "Annual")
        df_quarter = get_financial_statements(symbol, "Quarterly")

        ptype = st.radio(
            "نطاق التحليل:",
            ["Annual", "Quarterly"],
            horizontal=True,
            label_visibility="collapsed",
            key=f"fin_ptype_{symbol}"
        )

        df = df_annual if ptype == "Annual" else df_quarter

        if df is None or df.empty:
            st.warning("⚠️ لا توجد بيانات مالية محفوظة لهذا السهم.")
            st.info("👈 انتقل لتبويب 'إدارة البيانات' لرفع ملف أو جلب المعلومات.")
        else:
            metrics = get_advanced_fundamental_ratios(symbol)
            c1, c2, c3 = st.columns(3)
            c1.metric("المتانة (F-Score)", f"{metrics.get('Piotroski_Score',0)}/9", metrics.get("Financial_Health","-"))
            fv = metrics.get("Fair_Value_Graham", 0)
            c2.metric("قيمة جراهام", f"{fv:,.2f}" if fv and fv > 0 else "N/A")
            c3.write(f"**ملاحظات:** {metrics.get('Opinions', '-')}")
            st.markdown("---")

            try:
                plot_df = df.copy()
                if "date" in plot_df.columns:
                    plot_df["Year"] = plot_df["date"].dt.strftime("%Y-%m") if hasattr(plot_df["date"].dt, "strftime") else plot_df["date"].astype(str)
                    cols_to_plot = [c for c in ["revenue", "net_income", "operating_cash_flow"] if c in plot_df.columns and pd.to_numeric(plot_df[c], errors="coerce").fillna(0).sum() != 0]
                    if cols_to_plot:
                        fig = px.bar(
                            plot_df.sort_values("date") if "date" in plot_df.columns else plot_df,
                            x="Year",
                            y=cols_to_plot,
                            barmode="group",
                            title="الأداء المالي التاريخي"
                        )
                        st.plotly_chart(fig, use_container_width=True)
            except Exception:
                pass

            with st.expander("عرض الجدول التفصيلي"):
                # ✅ بدل st.dataframe: نفس تصميم جدول الاستثمار
                _render_table_like_trades(df, max_rows=600)

    with tab_data_mgmt:
        st.markdown("#### مصادر البيانات")
        t1, t2, t3 = st.tabs(["⚡ تحديث آلي (Yahoo)", "📂 استيراد ملف/نص", "✍️ إدخال يدوي شامل"])

        with t1:
            st.caption("جلب البيانات من Yahoo Finance مباشرة")
            if st.button("بدء المزامنة الآلية", key=f"sync_yahoo_{symbol}"):
                with st.spinner("جاري الاتصال..."):
                    ok, msg = sync_auto_yahoo(symbol)
                    if ok:
                        st.success(msg)
                        st.rerun()
                    else:
                        st.error(msg)

        with t2:
            render_data_import_ui_content(symbol)

        with t3:
            st.markdown("##### تسجيل البيانات المالية يدوياً")
            st.caption("أدخل البيانات اللازمة للتحليل المالي.")

            with st.form(f"manual_fin_entry_{symbol}"):
                col_meta1, col_meta2 = st.columns(2)
                f_date = col_meta1.date_input("تاريخ القوائم", date.today(), key=f"fin_date_{symbol}")
                f_type = col_meta2.selectbox("الفترة", ["Annual", "Quarterly"], key=f"fin_type_{symbol}")

                st.divider()
                st.markdown("**1. قائمة الدخل (Income Statement)**")
                c_inc1, c_inc2 = st.columns(2)
                rev = c_inc1.number_input("إجمالي الإيرادات", min_value=0.0, format="%.2f", key=f"fin_rev_{symbol}")
                net_inc = c_inc2.number_input("صافي الربح", format="%.2f", key=f"fin_net_{symbol}")

                st.divider()
                st.markdown("**2. قائمة التدفقات النقدية**")
                ocf = st.number_input("التدفق النقدي التشغيلي", help="Operating Cash Flow", format="%.2f", key=f"fin_ocf_{symbol}")

                st.divider()
                st.markdown("**3. المركز المالي (Balance Sheet)**")
                c_bs1, c_bs2 = st.columns(2)
                tot_assets = c_bs1.number_input("إجمالي الأصول", min_value=0.0, format="%.2f", key=f"fin_assets_{symbol}")
                tot_liab = c_bs2.number_input("إجمالي المطلوبات", min_value=0.0, format="%.2f", key=f"fin_liab_{symbol}")

                c_bs3, c_bs4 = st.columns(2)
                cur_assets = c_bs3.number_input("الأصول المتداولة", min_value=0.0, format="%.2f", key=f"fin_cur_assets_{symbol}")
                cur_liab = c_bs4.number_input("المطلوبات المتداولة", min_value=0.0, format="%.2f", key=f"fin_cur_liab_{symbol}")

                c_bs5, c_bs6 = st.columns(2)
                tot_equity = c_bs5.number_input("إجمالي حقوق الملكية", format="%.2f", key=f"fin_equity_{symbol}")
                lt_debt = c_bs6.number_input("الديون طويلة الأجل", min_value=0.0, format="%.2f", key=f"fin_ltdebt_{symbol}")

                st.divider()
                if st.form_submit_button("💾 حفظ البيانات"):
                    data = {
                        "revenue": rev,
                        "net_income": net_inc,
                        "operating_cash_flow": ocf,
                        "total_assets": tot_assets,
                        "total_liabilities": tot_liab,
                        "current_assets": cur_assets,
                        "current_liabilities": cur_liab,
                        "total_equity": tot_equity,
                        "long_term_debt": lt_debt,
                    }
                    if save_financial_record(symbol, str(f_date), data, f_type, "Manual_Full"):
                        st.success("تم الحفظ بنجاح!")
                        st.rerun()
                    else:
                        st.error("فشل الحفظ. تأكد من البيانات.")


# ========================================================
# 7) Analysis
# ========================================================

def view_analysis(fin):
    st.header("🔬 التحليل الشامل")
    trades = fin.get("all_trades", pd.DataFrame())

    if not trades.empty and "status" in trades.columns:
        status = _safe_status_series(trades)
        open_pos = trades[status == "open"].copy()
        st.subheader("📊 اختبار التحمل")
        res = run_stress_test(float(fin.get("market_val_open", 0)), open_pos)
        if res.get("scenarios"):
            c_stress, c_insight = st.columns([3, 1])
            with c_stress:
                sdf = pd.DataFrame(res["scenarios"])
                if not sdf.empty and "scenario" in sdf.columns and "impact_pct" in sdf.columns:
                    cmap = {}
                    try:
                        for r in res["scenarios"]:
                            if r.get("scenario") and r.get("color"):
                                cmap[r["scenario"]] = r["color"]
                    except Exception:
                        cmap = None

                    st.plotly_chart(
                        px.bar(
                            sdf,
                            x="scenario",
                            y="impact_pct",
                            color="scenario",
                            color_discrete_map=cmap if cmap else None,
                        ),
                        use_container_width=True,
                    )
            with c_insight:
                st.info(res.get("insight", ""))
        st.markdown("---")

    try:
        wl = fetch_table("watchlist")
    except Exception:
        wl = pd.DataFrame(columns=["symbol"])

    syms = []
    try:
        if not trades.empty and "symbol" in trades.columns:
            syms = list(set(trades["symbol"].astype(str).unique().tolist() + (wl["symbol"].astype(str).unique().tolist() if "symbol" in wl.columns else [])))
        else:
            syms = wl["symbol"].astype(str).unique().tolist() if "symbol" in wl.columns else []
    except Exception:
        syms = []

    c1, c2 = st.columns([1, 2])
    ns = c1.text_input("بحث", key="analysis_search")
    options = [ns] + syms if ns else syms
    sym = c2.selectbox("اختر السهم", options, key="analysis_symbol") if options else None

    if sym:
        sym = _normalize_symbol(sym)
        if not sym or sym == ".SR":
            st.warning("الرجاء إدخال رمز صحيح.")
            return

        n, sec = get_company_details(sym)
        st.markdown(f"### {n} ({sym})")
        tabs = st.tabs(["🤖 المستشار", "💰 مالي", "📈 فني", "🏛️ كلاسيكي", "📝 أطروحة"])

        with tabs[0]:
            rep = generate_ai_report(sym)

            if rep.get("__error__") or rep.get("__trace__"):
                st.error("فشل تشغيل المستشار (AI Engine).")
                st.code(rep.get("__trace__", ""))
                st.warning("يمكنك متابعة بقية التبويبات (مالي/فني/كلاسيكي) بينما نصلح المستشار.")
                return

            col = rep.get("color", "#666")

            st.markdown(
                f"<div style='padding:15px;border:2px solid {col};border-radius:10px;text-align:center;'>"
                f"<h3>{rep.get('recommendation','-')}</h3>"
                f"<p>{rep.get('strategy','-')}</p>"
                f"</div>",
                unsafe_allow_html=True
            )

            conf = int(rep.get("confidence", 0) or 0)
            conf_label = rep.get("confidence_label", "منخفضة")
            st.write(f"### 🎯 الثقة: {conf}% ({conf_label})")
            st.progress(min(max(conf, 0), 100))

            ex = rep.get("explainability", {}) or {}
            pos = ex.get("positives", []) or []
            neg = ex.get("negatives", []) or []
            notes = ex.get("notes", []) or []

            cc1, cc2 = st.columns(2)
            with cc1:
                st.write("✅ أسباب داعمة")
                for x in pos[:8]:
                    st.write(f"- {x}")
            with cc2:
                st.write("⚠️ أسباب سلبية / مخاطر")
                for x in neg[:8]:
                    st.write(f"- {x}")

            with st.expander("🧾 ملاحظات إضافية"):
                for x in notes:
                    st.write(f"- {x}")

            st.markdown("---")

            st.subheader("🧠 استراتيجياتي الخاصة")
            st.caption("اكتب قواعدك بصيغة بسيطة مثل: (تقاطع الماكد صعوداً + اختراق خط الصفر) أو (RSI فوق 70)")

            rule_text = st.text_area(
                "✍️ أدخل الاستراتيجية",
                key=f"user_rule_text_{sym}",
                height=110
            )

            col1, col2 = st.columns([1, 2])
            with col1:
                if st.button("💾 حفظ الاستراتيجية", key=f"save_rule_{sym}", type="primary"):
                    res = save_user_rule(rule_text, title="قاعدة من المستخدم", enabled=1)
                    if res.get("ok"):
                        st.success("✅ تم حفظ الاستراتيجية ودمجها مباشرة مع الذكاء")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error(f"لم يتم الحفظ: {res.get('reason','')}")
            with col2:
                st.caption("ملاحظة: الذكاء سيطبق القواعد تلقائياً عند توليد التقرير.")

            with st.expander("📌 عرض آخر الاستراتيجيات المحفوظة"):
                rules = load_user_rules(enabled_only=True, max_rows=10) or []
                if rules:
                    for r in rules:
                        st.write(f"- **{r.get('title','قاعدة')}**: {r.get('rule_text','')}")
                else:
                    st.info("لا توجد قواعد محفوظة بعد.")

            st.markdown("---")

            if run_backtest:
                if st.button("🧪 تشغيل Backtest على هذا السهم", key=f"bt_{sym}"):
                    try:
                        data = get_chart_history(sym, "2y")
                        _, sec2 = get_company_details(sym)

                        rec_txt = str(rep.get("recommendation", "")).lower()
                        trend_txt = str(rep.get("trend", "")).strip()

                        if ("strong buy" in rec_txt) or ("شراء" in rec_txt):
                            strategy = "Trend"
                        elif ("مضاربة" in rec_txt) or ("⚡" in rec_txt):
                            strategy = "Sniper"
                        else:
                            strategy = "Trend" if trend_txt == "صاعد" else "Sniper"

                        resbt = run_backtest(data, strategy, 100000, symbol=sym, sector=sec2)

                        if resbt:
                            st.success(f"✅ اكتمل الاختبار (Strategy: {resbt.get('strategy_name_ar', strategy)})")
                            st.metric("العائد", f"{resbt.get('return_pct', 0):.2f}%")
                            if "df" in resbt and isinstance(resbt["df"], pd.DataFrame) and "Portfolio_Value" in resbt["df"]:
                                st.line_chart(resbt["df"]["Portfolio_Value"])

                            # ✅ بدل st.dataframe: نفس تصميم جدول الاستثمار
                            with st.expander("سجل الصفقات"):
                                tlog = resbt.get("trades_log", pd.DataFrame())
                                _render_table_like_trades(
                                    tlog,
                                    cols_spec=[
                                        ("Date", "التاريخ", "date"),
                                        ("Type", "النوع", "badge"),
                                        ("Price", "السعر", "money"),
                                        ("Qty", "الكمية", "money"),
                                        ("Cash", "الكاش", "money"),
                                        ("Value", "القيمة", "money"),
                                    ],
                                    max_rows=500
                                )
                        else:
                            st.warning("⚠️ لم يرجع الاختبار نتيجة (قد تكون البيانات غير كافية).")

                    except Exception as e:
                        st.error(f"Backtest Error: {e}")
            else:
                st.caption("Backtester غير متوفر حالياً.")
                if bt_import_error:
                    st.code(bt_import_error)

            cA, cB = st.columns(2)
            with cA:
                st.write("فني:")
                for x in rep.get("tech_reasons", []):
                    st.write(f"- {x}")
            with cB:
                st.write("مالي:")
                for x in rep.get("fund_reasons", []):
                    st.write(f"- {x}")

        with tabs[1]:
            render_financial_dashboard_ui(sym)

        with tabs[2]:
            render_technical_chart(sym)

        with tabs[3]:
            render_classical_analysis(sym)

        with tabs[4]:
            th = get_thesis(sym)
            txt = th["thesis_text"] if (isinstance(th, dict) and "thesis_text" in th) else (
                th.thesis_text if th is not None and hasattr(th, "thesis_text") else ""
            )
            with st.form(f"th_{sym}"):
                nt = st.text_area("نص الأطروحة", value=txt)
                if st.form_submit_button("حفظ"):
                    save_thesis(sym, nt, 0, "Hold")
                    st.success("تم")


# ========================================================
# 8) Other Pages
# ========================================================

def view_backtester_ui(fin):
    st.header("🧪 المختبر")

    if not run_backtest:
        st.warning("Backtester غير متوفر حالياً.")
        if bt_import_error:
            st.code(bt_import_error)
        st.info("✅ الحل: تأكد أنك استبدلت backtester.py بالنسخة الجديدة التي فيها STRATEGY_CATALOG و list_strategies.")
        return

    s = st.text_input("رمز السهم", "1120", key="lab_symbol")
    cap = st.number_input("رأس المال", min_value=1000.0, value=100000.0, step=1000.0, key="lab_cap")

    strat = _select_strategy_ui(key_prefix="lab")

    period = st.selectbox("الفترة التاريخية", ["6mo", "1y", "2y", "5y", "10y", "max"], index=3, key="lab_period")

    if st.button("بدء", key="bt_run"):
        try:
            s_norm = _normalize_symbol(s)
            st.caption(f"🔎 الرمز: {s_norm} | الفترة: {period} | الاستراتيجية: {strat}")

            data = get_chart_history(s_norm, period)

            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                st.error("❌ لم يتم جلب بيانات (DataFrame فارغ)")
                return

            if not isinstance(data, pd.DataFrame):
                data = pd.DataFrame(data)

            st.caption(f"📦 rows={len(data)} cols={len(data.columns)}")
            try:
                st.caption(f"🗓️ من: {data.index.min()}  إلى: {data.index.max()}")
            except Exception:
                pass

            # ✅ بدل st.dataframe: نفس تصميم جدول الاستثمار + تثبيت التاريخ كعمود
            preview = data.tail(20).copy()
            try:
                preview = preview.reset_index()
                if "index" in preview.columns:
                    preview = preview.rename(columns={"index": "date"})
            except Exception:
                pass

            # حاول نعرض OHLCV لو موجودة
            cols = []
            if "date" in preview.columns: cols.append(("date", "التاريخ", "date"))
            for k, lab in [("Open","الافتتاح"), ("High","الأعلى"), ("Low","الأدنى"), ("Close","الإغلاق"), ("Volume","الحجم")]:
                if k in preview.columns:
                    cols.append((k, lab, "money" if k != "Volume" else "number"))

            _render_table_like_trades(preview, cols_spec=cols if cols else None, max_rows=30)

            if len(data) < 120:
                st.warning("⚠️ أقل من 120 شمعة — غالبًا لن تظهر إشارات (جرّب 5y أو max).")

            if "Close" not in data.columns and "close" not in data.columns:
                st.error("❌ لا يوجد عمود Close في البيانات")
                st.write("الأعمدة:", list(data.columns))
                return

            _, sec = get_company_details(s_norm)

            res = run_backtest(data, str(strat), cap, symbol=s_norm, sector=sec)

            if res:
                st.success(f"✅ اكتمل الاختبار ({res.get('strategy_name_ar', strat)})")
                st.metric("العائد", f"{res.get('return_pct', 0):.2f}%")
                if "df" in res and isinstance(res["df"], pd.DataFrame) and "Portfolio_Value" in res["df"]:
                    st.line_chart(res["df"]["Portfolio_Value"])

                # ✅ بدل st.dataframe: نفس تصميم جدول الاستثمار
                with st.expander("سجل الصفقات"):
                    tlog = res.get("trades_log", pd.DataFrame())
                    _render_table_like_trades(
                        tlog,
                        cols_spec=[
                            ("Date", "التاريخ", "date"),
                            ("Type", "النوع", "badge"),
                            ("Price", "السعر", "money"),
                            ("Qty", "الكمية", "money"),
                            ("Cash", "الكاش", "money"),
                            ("Value", "القيمة", "money"),
                        ],
                        max_rows=800
                    )
            else:
                st.warning("⚠️ لم يرجع الاختبار نتيجة.")
                st.info("إذا البيانات كبيرة، فالغالب أن الاستراتيجية لم تعطِ إشارات خلال الفترة.")

        except Exception as e:
            st.error(f"Backtest Error: {e}")


def render_pulse_dashboard():
    st.header("نبض السوق")
    try:
        trades = fetch_table("trades")
    except Exception:
        trades = pd.DataFrame()

    syms = list(trades["symbol"].astype(str).unique()) if (not trades.empty and "symbol" in trades.columns) else []
    syms = _clean_symbols_list(syms)
    if syms:
        d = fetch_batch_data(syms)
        cols = st.columns(4)
        for i, (s, v) in enumerate(d.items()):
            prev = v.get("prev_close") or 0
            chg = ((v.get("price", 0) - prev) / prev) * 100 if prev else 0
            with cols[i % 4]:
                render_ticker_card(s, "سهم", v.get("price", 0), chg)
    else:
        st.info("لا توجد رموز لعرض نبض السوق.")


def view_add_trade():
    st.header("➕ إضافة صفقة")
    with st.form("add_t"):
        c1, c2 = st.columns(2)
        s_raw = c1.text_input("رمز السهم (مثال: 1120)", key="add_sym")
        typ = c2.selectbox("نوع الصفقة", ["استثمار", "مضاربة", "صكوك"], key="add_typ")
        c3, c4, c5 = st.columns(3)
        q = c3.number_input("الكمية", min_value=1.0, key="add_q")
        p = c4.number_input("السعر", min_value=0.0, key="add_p")
        d = c5.date_input("التاريخ", date.today(), key="add_d")

        if st.form_submit_button("حفظ"):
            valid, msg = validate_trade_inputs(q, p)
            if valid:
                s = _normalize_symbol(s_raw)
                nm, sec = get_company_details(s)
                at = "Sukuk" if typ == "صكوك" else "Stock"
                execute_query(
                    "INSERT INTO trades (symbol, company_name, sector, asset_type, quantity, entry_price, strategy, status, date) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'Open',%s)",
                    (s, nm, sec, at, q, p, typ, str(d))
                )
                st.success("تم")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)


def view_tools():
    st.header("🛠️ أدوات")
    st.info("حاسبة الزكاة (قريباً)")


def view_settings():
    st.header("الإعدادات")

    if st.button("🔎 تشخيص قاعدة البيانات", key="db_diag"):
        rep = db_healthcheck()
        if not rep.get("connected"):
            st.error("غير متصل بقاعدة البيانات")
        else:
            st.success("✅ اتصال ناجح")
            st.json(rep.get("db", {}))
            st.write("### Counts")
            st.json(rep.get("counts", {}))
            if rep.get("dup_tables"):
                st.error(f"⚠️ يوجد ازدواج جداول: {rep['dup_tables']}")
            else:
                st.success("✅ لا يوجد ازدواج جداول (Case Safe)")

    st.markdown("---")
    if st.button("نسخة احتياطية", key="backup_btn"):
        d, n = create_smart_backup()
        if d:
            st.download_button("تحميل", d, n)


# ========================================================
# 9) Router
# ========================================================

def router():
    _ensure_ui_once()

    if "page" not in st.session_state:
        st.session_state.page = "home"

    render_navbar()
    pg = st.session_state.page

    # ✅ نحسب مرة واحدة فقط
    fin = calculate_portfolio_metrics()

    if pg == "home":
        view_dashboard(fin)
    elif pg == "spec":
        view_portfolio(fin, "spec")
    elif pg == "invest":
        view_portfolio(fin, "invest")
    elif pg == "sukuk":
        view_sukuk_portfolio(fin)
    elif pg == "analysis":
        view_analysis(fin)
    elif pg == "cash":
        view_cash_log(fin)
    elif pg == "backtest":
        view_backtester_ui(fin)
    elif pg == "pulse":
        render_pulse_dashboard()
    elif pg == "add":
        view_add_trade()
    elif pg == "tools":
        view_tools()
    elif pg == "settings":
        view_settings()
    elif pg == "update":
        with st.spinner("جاري التحديث..."):
            update_prices()
        st.cache_data.clear()
        st.rerun()
    else:
        st.session_state.page = "home"
        st.rerun()
```0