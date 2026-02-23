# views/portfolio.py
import streamlit as st
from feature_flags import get_flag
import pandas as pd
from datetime import date

from components import render_kpi, render_custom_table, render_ticker_card, safe_fmt
from database import execute_query, fetch_table
from market_data import fetch_batch_data
from analytics import compute_portfolio_xirr
from data_source import get_company_details
from security import validate_trade_inputs
from views.shared import _safe_status_series, _clean_symbols_list, _normalize_symbol

# ✅ Portfolio risk engine (safe import)
try:
    from ai_engine_core.portfolio import (
        calculate_portfolio_risk_score,
        run_stress_test,
        generate_rebalancing_suggestions,
        portfolio_risk_gates,
    )
except Exception:
    calculate_portfolio_risk_score = None
    run_stress_test = None
    generate_rebalancing_suggestions = None
    portfolio_risk_gates = None


def _sf(x, default=0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def _safe_cash_pct(fin: dict, open_market_val: float) -> float:
    """
    يأخذ cash_pct من analytics إن توفر،
    وإلا يحسبه: cash / (cash + open_market_val)
    """
    try:
        if isinstance(fin, dict) and "cash_pct" in fin:
            return float(_sf(fin.get("cash_pct", 0.0), 0.0))
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at views/portfolio.py:47')

    cash = _sf((fin or {}).get("cash", 0.0), 0.0) if isinstance(fin, dict) else 0.0
    pv = float(max(0.0, cash + _sf(open_market_val, 0.0)))
    return float((cash / pv) * 100.0) if pv > 0 else 0.0


def _risk_score_badge(score: float) -> str:
    score = float(_sf(score, 0.0))
    if score >= 75:
        return "danger"
    if score >= 55:
        return "warn"
    if score >= 35:
        return "neutral"
    return "success"


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

    df = fin.get("all_trades", pd.DataFrame()) if isinstance(fin, dict) else pd.DataFrame()
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

        # =========================================================
        # 🛡️ لوحة مخاطر المحفظة (NEW)
        # =========================================================
        with st.expander("🛡️ لوحة مخاطر المحفظة (بوابات + Stress Test + اقتراحات)", expanded=True):
            cash = _sf((fin or {}).get("cash", 0.0), 0.0) if isinstance(fin, dict) else 0.0
            cash_pct = _safe_cash_pct(fin or {}, total_market)
            portfolio_value = _sf((fin or {}).get("portfolio_value", cash + total_market), cash + total_market)


            # -----------------------------------------------------
            # 📈 XIRR (اختياري) — لا يظهر إلا بتفعيل Feature Flag
            # -----------------------------------------------------
            if get_flag("enable_xirr", False):
                try:
                    dep = (fin or {}).get("deposits", pd.DataFrame())
                    wit = (fin or {}).get("withdrawals", pd.DataFrame())
                    ret = (fin or {}).get("returns", pd.DataFrame())

                    with st.expander("📈 عائد المحفظة الحقيقي XIRR (تجريبي)", expanded=False):
                        st.caption("يعتمد على سجل الإيداعات/السحوبات/العوائد + القيمة الحالية للمحفظة.")
                        xirr, method = compute_portfolio_xirr(dep, wit, ret, ending_value=portfolio_value)
                        if xirr is None:
                            st.warning(f"⚠️ لم يمكن حساب XIRR: {method}. تأكد من وجود تدفقات نقدية كافية وقيمة محفظة > 0.")
                        else:
                            st.metric("XIRR السنوي", f"{xirr*100:,.2f}%")
                            st.caption(f"طريقة الحساب: {method}")
                except Exception as e:
                    st.error(f"تعذر حساب XIRR: {e}")

            c_r1, c_r2, c_r3, c_r4 = st.columns(4)
            with c_r1:
                render_kpi("قيمة المحفظة", safe_fmt(portfolio_value), "blue")
            with c_r2:
                render_kpi("الكاش", safe_fmt(cash), "neutral")
            with c_r3:
                render_kpi("نسبة الكاش", f"{cash_pct:.1f}%", "success" if cash_pct >= 15 else ("warn" if cash_pct >= 8 else "danger"), "٪")

            risk_score = None
            if callable(calculate_portfolio_risk_score) and isinstance(op, pd.DataFrame) and not op.empty:
                try:
                    risk_score = float(calculate_portfolio_risk_score(op, cash_pct))
                except Exception:
                    risk_score = None

            with c_r4:
                if risk_score is None:
                    render_kpi("Risk Score", "N/A", "neutral")
                else:
                    render_kpi("Risk Score", f"{risk_score:.0f}/100", _risk_score_badge(risk_score))

            # Gates
            if callable(portfolio_risk_gates) and isinstance(op, pd.DataFrame) and not op.empty:
                try:
                    gates = portfolio_risk_gates(op, cash_pct)
                except Exception:
                    gates = {"pass": True, "reasons": [], "risk_score": risk_score or 0.0}
            else:
                gates = {"pass": True, "reasons": [], "risk_score": risk_score or 0.0}

            if gates.get("pass", True):
                st.success("✅ بوابات المخاطر: PASS — الوضع مقبول")
            else:
                st.warning("⚠️ بوابات المخاطر: FAIL — يفضل تخفيف المخاطر/رفع الكاش")
                for r in (gates.get("reasons") or [])[:8]:
                    if str(r).strip():
                        st.write(f"- {r}")

            # Stress test
            if callable(run_stress_test):
                try:
                    stress = run_stress_test(portfolio_value, op)
                except Exception:
                    stress = {"scenarios": [], "insight": "غير متاح"}

                st.markdown("**📉 Stress Test (تأثير تقديري على المحفظة)**")
                if stress.get("insight"):
                    st.caption(stress["insight"])

                sc = stress.get("scenarios") or []
                if sc:
                    df_sc = pd.DataFrame(sc)
                    # عرض مرتب
                    if "impact_pct" in df_sc.columns:
                        df_sc["impact_pct"] = pd.to_numeric(df_sc["impact_pct"], errors="coerce").fillna(0.0).astype(float)
                        df_sc["impact_pct"] = df_sc["impact_pct"].round(2)

                    # ✅ توحيد شكل الجدول (نفس جدول الصفقات) + إصلاح TypeError
                    # render_custom_table في components.py لا يدعم key/use_container_width
                    cols = []
                    if "scenario" in df_sc.columns:
                        cols.append(("scenario", "السيناريو", "text"))
                    if "name" in df_sc.columns and ("scenario" not in df_sc.columns):
                        cols.append(("name", "السيناريو", "text"))
                    if "impact_pct" in df_sc.columns:
                        cols.append(("impact_pct", "الأثر %", "percent"))
                    if "impact_value" in df_sc.columns:
                        cols.append(("impact_value", "الأثر (قيمة)", "money"))
                    if "impact" in df_sc.columns and ("impact_value" not in df_sc.columns):
                        cols.append(("impact", "الأثر", "money"))
                    if "note" in df_sc.columns:
                        cols.append(("note", "ملاحظة", "text"))

                    # fallback: لو ما عرفنا الأعمدة، اعرض أول 6 أعمدة
                    if not cols:
                        for c in list(df_sc.columns)[:6]:
                            cols.append((c, str(c), "text"))

                    render_custom_table(df_sc, cols)
                else:
                    st.info("لا توجد سيناريوهات متاحة حالياً.")

            # Rebalancing suggestions
            if callable(generate_rebalancing_suggestions):
                try:
                    sugg = generate_rebalancing_suggestions(op, cash_pct)
                except Exception:
                    sugg = []
            else:
                sugg = []

            st.markdown("**🧭 اقتراحات إعادة توازن**")
            if sugg:
                for level, text in sugg[:10]:
                    level = str(level or "").lower()
                    txt = str(text or "").strip()
                    if not txt:
                        continue
                    if "danger" in level:
                        st.error(txt)
                    elif "priority" in level:
                        st.warning(txt)
                    elif "warn" in level:
                        st.warning(txt)
                    else:
                        st.info(txt)
            else:
                st.info("لا توجد اقتراحات حالياً — الوضع مستقر.")

        # =========================================================
        # ✅ جدول الصفقات القائمة (كما هو)
        # =========================================================
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

            symbols = _clean_symbols_list(op["symbol"].astype(str).tolist()) if "symbol" in op.columns else []
            try:
                live_data = fetch_batch_data(symbols) if symbols else {}
            except Exception:
                live_data = {}

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
                    (s, nm, sec, at, q, p, typ, str(d))
                )
                st.success("تم")
                st.cache_data.clear()
                st.rerun()
            else:
                st.error(msg)
