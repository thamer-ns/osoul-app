# views_impl.py
# ✅ Real implementation layer (kept minimal after moving pages into ui.pages.*)
# NOTE:
# - Removed: view_analysis + financial/AI/chart-heavy utilities (now live in ui/pages/analysis/*)
# - Kept only pages still imported by ui/router.py:
#   view_cash_log, view_backtester_ui, render_pulse_dashboard, view_add_trade, view_tools, view_settings

import streamlit as st
import pandas as pd
from datetime import date
import traceback

from components import (
    render_kpi,
    render_custom_table,
    render_ticker_card,
    safe_fmt,
)

from analytics import create_smart_backup
from database import execute_query, fetch_table, db_healthcheck
from market_data import get_chart_history, fetch_batch_data
from data_source import get_company_details
from security import validate_trade_inputs

from ui.common import normalize_symbol as _normalize_symbol
from ui.common import clean_symbols_list as _clean_symbols_list


# ========================================================
# 🛡️ Backtester (Fail-Safe)
# ========================================================

bt_import_error = None
try:
    from backtester import run_backtest, list_strategies
except Exception as e:
    run_backtest = None
    list_strategies = lambda: []
    bt_import_error = repr(e)


def _select_strategy_ui(key_prefix: str = "lab") -> str:
    """
    يدعم list_strategies سواء رجعت:
    - ["Trend","Sniper"]
    - [("Trend","ترند"), ("Sniper","قناص")]
    - [{"key":"Trend","name":"ترند"}]
    ويرجع دائمًا قيمة strategy كنص (string) لتفادي أخطاء tuple/title وغيرها
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


def _to_float(x, default=0.0):
    try:
        if x is None or x == "":
            return default
        return float(x)
    except Exception:
        return default


# ========================================================
# 1) Cash Log
# ========================================================

def view_cash_log(fin):
    st.header("💰 السيولة والسجلات المالية")

    dep = fin.get("deposits", pd.DataFrame())
    wit = fin.get("withdrawals", pd.DataFrame())
    ret = fin.get("returns", pd.DataFrame())

    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi(
            "إجمالي الإيداعات",
            safe_fmt(dep["amount"].sum() if (not dep.empty and "amount" in dep.columns) else 0),
            "success",
            "📥",
        )
    with c2:
        render_kpi(
            "إجمالي السحوبات",
            safe_fmt(wit["amount"].sum() if (not wit.empty and "amount" in wit.columns) else 0),
            "danger",
            "📤",
        )
    with c3:
        render_kpi(
            "إجمالي العوائد",
            safe_fmt(ret["amount"].sum() if (not ret.empty and "amount" in ret.columns) else 0),
            "blue",
            "🎁",
        )

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
                        execute_query(
                            "INSERT INTO deposits (date, amount, note) VALUES (%s,%s,%s)",
                            (str(d), a, n),
                        )
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not dep.empty:
            render_custom_table(
                dep.sort_values("date", ascending=False) if "date" in dep.columns else dep,
                cols_base,
            )
            st.markdown("---")
            with st.expander("✏️ تعديل سجل إيداع سابق"):
                if "id" in dep.columns:
                    dep_map = {
                        f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"]
                        for _, row in dep.iterrows()
                    }
                    sel_dep = st.selectbox("اختر العملية للتعديل:", list(dep_map.keys()), key="edit_dep_sel")
                    if sel_dep:
                        tid = dep_map[sel_dep]
                        curr = dep[dep["id"] == tid].iloc[0]
                        with st.form(f"edit_dep_form_{tid}"):
                            na = st.number_input(
                                "المبلغ الصحيح",
                                value=float(curr.get("amount", 0)),
                                key=f"dep_fix_amt_{tid}",
                            )
                            nd = st.date_input(
                                "التاريخ الصحيح",
                                pd.to_datetime(curr.get("date", date.today())).date(),
                                key=f"dep_fix_date_{tid}",
                            )
                            nn = st.text_input(
                                "ملاحظة",
                                value=str(curr.get("note", "") or ""),
                                key=f"dep_fix_note_{tid}",
                            )
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query(
                                    "UPDATE deposits SET amount=%s, date=%s, note=%s WHERE id=%s",
                                    (na, str(nd), nn, tid),
                                )
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
                        execute_query(
                            "INSERT INTO withdrawals (date, amount, note) VALUES (%s,%s,%s)",
                            (str(d), a, n),
                        )
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not wit.empty:
            render_custom_table(
                wit.sort_values("date", ascending=False) if "date" in wit.columns else wit,
                cols_base,
            )
            st.markdown("---")
            with st.expander("✏️ تعديل سجل سحب سابق"):
                if "id" in wit.columns:
                    wit_map = {
                        f"{row.get('date','-')} - {row.get('amount','-')} ({row.get('note','')})": row["id"]
                        for _, row in wit.iterrows()
                    }
                    sel_wit = st.selectbox("اختر العملية للتعديل:", list(wit_map.keys()), key="edit_wit_sel")
                    if sel_wit:
                        tid = wit_map[sel_wit]
                        curr = wit[wit["id"] == tid].iloc[0]
                        with st.form(f"edit_wit_form_{tid}"):
                            na = st.number_input(
                                "المبلغ الصحيح",
                                value=float(curr.get("amount", 0)),
                                key=f"wit_fix_amt_{tid}",
                            )
                            nd = st.date_input(
                                "التاريخ الصحيح",
                                pd.to_datetime(curr.get("date", date.today())).date(),
                                key=f"wit_fix_date_{tid}",
                            )
                            nn = st.text_input(
                                "ملاحظة",
                                value=str(curr.get("note", "") or ""),
                                key=f"wit_fix_note_{tid}",
                            )
                            if st.form_submit_button("حفظ التعديلات"):
                                execute_query(
                                    "UPDATE withdrawals SET amount=%s, date=%s, note=%s WHERE id=%s",
                                    (na, str(nd), nn, tid),
                                )
                                st.success("تم التعديل")
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
                        execute_query(
                            "INSERT INTO returnsgrants (date, symbol, amount) VALUES (%s,%s,%s)",
                            (str(d), s, a),
                        )
                        st.success("تم")
                        st.cache_data.clear()
                        st.rerun()

        if not ret.empty:
            render_custom_table(
                ret.sort_values("date", ascending=False) if "date" in ret.columns else ret,
                [("date", "التاريخ", "date"), ("symbol", "السهم", "text"), ("amount", "المبلغ", "money")],
            )


# ========================================================
# 2) Backtester UI
# ========================================================

def view_backtester_ui(fin):
    st.header("🧪 المختبر")

    if not run_backtest:
        st.warning("Backtester غير متوفر حالياً.")
        if bt_import_error:
            st.code(bt_import_error)
        st.info("✅ الحل: تأكد أن backtester.py يحتوي list_strategies و run_backtest بشكل صحيح.")
        return

    st.markdown("#### ⚙️ إعدادات الاختبار")
    cA, cB, cC = st.columns([1.2, 1.2, 1.6])
    s = cA.text_input("رمز السهم", "1120", key="lab_symbol", help="اكتب 1120 أو 1120.SR")
    cap = cB.number_input("رأس المال", min_value=1000.0, value=100000.0, step=1000.0, key="lab_cap")
    period = cC.selectbox("الفترة التاريخية", ["6mo", "1y", "2y", "5y", "10y", "max"], index=3, key="lab_period")

    strat = _select_strategy_ui(key_prefix="lab")
    st.caption("💡 إذا الاستراتيجية تعتمد على مؤشرات طويلة، اختر فترة أكبر (مثل 5y أو 10y).")

    if st.button("🚀 بدء الاختبار", key="bt_run", type="primary"):
        try:
            s_norm = _normalize_symbol(s)
            st.caption(f"🔎 الرمز: {s_norm} | الفترة: {period} | الاستراتيجية: {strat}")

            with st.spinner("جاري جلب البيانات التاريخية..."):
                data = get_chart_history(s_norm, period)

            if data is None or (isinstance(data, pd.DataFrame) and data.empty):
                st.error("❌ لم يتم جلب بيانات (DataFrame فارغ)")
                return

            if not isinstance(data, pd.DataFrame):
                data = pd.DataFrame(data)

            if "Close" not in data.columns and "close" not in data.columns:
                st.error("❌ لا يوجد عمود Close في البيانات")
                st.write("الأعمدة:", list(data.columns))
                return

            # القطاع
            try:
                info = get_company_details(s_norm)
                if isinstance(info, (list, tuple)) and len(info) >= 2:
                    sec = info[1]
                elif isinstance(info, dict):
                    sec = info.get("sector") or info.get("Sector") or ""
                else:
                    sec = ""
            except Exception:
                sec = ""

            with st.spinner("🧪 جاري تنفيذ الاستراتيجية على البيانات..."):
                res = run_backtest(data, str(strat), float(cap), symbol=s_norm, sector=sec)

            if not res:
                st.warning("⚠️ لم يرجع الاختبار نتيجة.")
                return

            st.session_state["__last_bt_result__"] = res
            st.success(f"✅ اكتمل الاختبار ({res.get('strategy_name_ar', strat)})")

        except Exception as e:
            st.error(f"Backtest Error: {e}")
            st.code(traceback.format_exc())

    res = st.session_state.get("__last_bt_result__")
    if res:
        st.markdown("---")
        st.markdown("#### 📊 النتائج")

        t_sum, t_curve, t_trades, t_raw = st.tabs(["ملخص", "منحنى المحفظة", "الصفقات", "خام"])

        with t_sum:
            kpis = {
                "return_pct": ("العائد %", "percent"),
                "final_value": ("القيمة النهائية", "money"),
                "max_drawdown_pct": ("أقصى سحب %", "percent"),
                "win_rate": ("نسبة النجاح", "percent"),
                "trades_count": ("عدد الصفقات", "number"),
                "sharpe": ("Sharpe", "number"),
            }

            cols = st.columns(4)
            idx = 0
            for k, (label, typ) in kpis.items():
                if k in res:
                    v = res.get(k)
                    if typ == "percent":
                        txt = f"{_to_float(v, 0):.2f}%"
                    elif typ == "money":
                        txt = safe_fmt(_to_float(v, 0))
                    elif typ == "number":
                        try:
                            txt = str(int(_to_float(v, 0)))
                        except Exception:
                            txt = str(v)
                    else:
                        try:
                            txt = f"{_to_float(v, 0):.2f}"
                        except Exception:
                            txt = str(v)

                    with cols[idx % 4]:
                        st.metric(label, txt)
                    idx += 1

            if isinstance(res.get("metrics"), dict) and res["metrics"]:
                st.markdown("---")
                st.markdown("**📌 مؤشرات إضافية**")
                mdf = pd.DataFrame([{"Metric": k, "Value": v} for k, v in res["metrics"].items()])
                st.dataframe(mdf, use_container_width=True)

        with t_curve:
            df_curve = res.get("df")
            if isinstance(df_curve, pd.DataFrame) and not df_curve.empty:
                col = None
                for cand in ["Portfolio_Value", "portfolio_value", "equity", "Equity", "value"]:
                    if cand in df_curve.columns:
                        col = cand
                        break
                if col:
                    st.line_chart(df_curve[col])
                else:
                    st.info("لا يوجد عمود منحنى واضح داخل df.")
                    st.dataframe(df_curve.head(50), use_container_width=True)
            else:
                st.info("لا يوجد DataFrame منحنى داخل النتيجة.")

        with t_trades:
            trades_df = res.get("trades") or res.get("trades_df")
            if isinstance(trades_df, pd.DataFrame) and not trades_df.empty:
                st.dataframe(trades_df, use_container_width=True)
            else:
                st.info("لا توجد صفقات مسجلة داخل نتيجة الاختبار (أو الاستراتيجية لا ترجعها).")

        with t_raw:
            st.json({k: v for k, v in res.items() if k != "df"})


# ========================================================
# 3) Pulse Dashboard
# ========================================================

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


# ========================================================
# 4) Add Trade
# ========================================================

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

                try:
                    info = get_company_details(s)
                    if isinstance(info, (list, tuple)) and len(info) >= 2:
                        nm, sec = info[0], info[1]
                    elif isinstance(info, dict):
                        nm = info.get("name") or info.get("Name") or s
                        sec = info.get("sector") or info.get("Sector") or ""
                    else:
                        nm, sec = s, ""
                except Exception:
                    nm, sec = s, ""

                at = "Sukuk" if typ == "صكوك" else "Stock"
                execute_query(
                    "INSERT INTO trades (symbol, company_name, sector, asset_type, quantity, entry_price, strategy, status, date) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,'Open',%s)",
                    (s, nm, sec, at, q, p, typ, str(d)),
                )
                st.success("تم")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)


# ========================================================
# 5) Tools
# ========================================================

def view_tools():
    st.header("🛠️ أدوات")
    st.info("حاسبة الزكاة (قريباً)")


# ========================================================
# 6) Settings
# ========================================================

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
