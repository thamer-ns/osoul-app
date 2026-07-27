"""Portfolio signal center powered by the v4 decision contract."""
from __future__ import annotations

import math
from typing import Any

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi
from views.shared import _extract_ai, _generate_ai_report_flex, _normalize_symbol

TIMEFRAMES = {
    "1m": "1 دقيقة", "5m": "5 دقائق", "15m": "15 دقيقة",
    "30m": "30 دقيقة", "1h": "ساعة", "4h": "4 ساعات",
    "1d": "يومي", "1wk": "أسبوعي", "1mo": "شهري",
}


def _safe_number(value: Any, default: float = 0.0) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return float(default)
    return number if math.isfinite(number) else float(default)


def _recommendation_kind(recommendation: str, direction: str = "neutral") -> str:
    text = str(recommendation or "").casefold()
    if any(word in text for word in ("شراء", "صاعد", "تجميع", "buy", "long")):
        return "buy"
    if any(word in text for word in ("بيع", "هابط", "خروج", "تحوط", "sell", "short")):
        return "sell"
    return direction if direction in {"buy", "sell"} else "neutral"


def _decision_fields(extracted: dict[str, Any]) -> dict[str, Any]:
    raw = extracted.get("raw") if isinstance(extracted.get("raw"), dict) else extracted
    raw = raw if isinstance(raw, dict) else {}
    decision = raw.get("decision_engine") if isinstance(raw.get("decision_engine"), dict) else {}
    plan = decision.get("plan") if isinstance(decision.get("plan"), dict) else raw.get("risk_plan")
    plan = plan if isinstance(plan, dict) else {}
    consensus = raw.get("school_consensus") if isinstance(raw.get("school_consensus"), dict) else {}
    geometry = raw.get("plan_geometry") if isinstance(raw.get("plan_geometry"), dict) else {}
    return {
        "direction": str(raw.get("direction") or decision.get("direction") or "neutral"),
        "direction_score": _safe_number(raw.get("direction_score", decision.get("direction_score"))),
        "lifecycle": str(raw.get("lifecycle_status") or decision.get("status") or "NO_SETUP"),
        "stage": str(raw.get("analysis_stage") or decision.get("stage") or "راقب"),
        "opportunity": str(raw.get("opportunity_label") or decision.get("opportunity_label") or "غير مصنف"),
        "plan": plan,
        "plan_id": plan.get("plan_id") or (raw.get("engine_meta") or {}).get("plan_id"),
        "consensus": consensus,
        "geometry": geometry,
    }


def _entry_text(extracted: dict[str, Any], plan: dict[str, Any]) -> str:
    low = plan.get("entry_low")
    high = plan.get("entry_high")
    if low is not None and high is not None:
        return f"{_safe_number(low):.2f} – {_safe_number(high):.2f}"
    entry = plan.get("entry")
    return "—" if entry is None else f"{_safe_number(entry):.2f}"


def _symbol_universe(finance: dict[str, Any]) -> list[str]:
    frames = []
    for key in ("open_positions_df", "all_trades"):
        value = finance.get(key)
        if isinstance(value, pd.DataFrame) and not value.empty:
            frames.append(value)
    values: list[str] = []
    for frame in frames:
        if "status" in frame.columns:
            status = frame["status"].astype(str).str.strip().str.lower()
            frame = frame[status == "open"]
        if "asset_type" in frame.columns:
            asset = frame["asset_type"].astype(str).str.strip().str.lower()
            frame = frame[~asset.eq("sukuk")]
        if "symbol" in frame.columns:
            values.extend(frame["symbol"].dropna().astype(str).tolist())
    output = sorted({_normalize_symbol(value) for value in values if str(value).strip()})
    return [value for value in output if value and value != ".SR"]


def _cache() -> dict[str, Any]:
    value = st.session_state.get("signals_v4_cache")
    if not isinstance(value, dict):
        value = {}
        st.session_state["signals_v4_cache"] = value
    return value


def _run(symbols: list[str], timeframes: list[str], *, refresh: bool) -> list[dict[str, Any]]:
    cache = _cache()
    rows = []
    for symbol in symbols:
        for timeframe in timeframes:
            key = f"{symbol}|{timeframe}"
            if refresh:
                cache.pop(key, None)
            if key not in cache:
                cache[key] = _generate_ai_report_flex(symbol, timeframe=timeframe)
            report = cache[key] if isinstance(cache[key], dict) else {}
            extracted = _extract_ai(report)
            fields = _decision_fields({"raw": report, **(extracted if isinstance(extracted, dict) else {})})
            plan = fields["plan"]
            consensus = fields["consensus"]
            geometry = fields["geometry"]
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "stage": fields["stage"],
                    "lifecycle": fields["lifecycle"],
                    "direction": fields["direction"],
                    "direction_score": fields["direction_score"],
                    "opportunity": fields["opportunity"],
                    "confidence": _safe_number(report.get("confidence")),
                    "schools": int(consensus.get("school_count") or 0),
                    "school_names": " + ".join(str(item) for item in consensus.get("school_names") or []),
                    "consensus_strength": _safe_number(consensus.get("strength")),
                    "entry": _entry_text(extracted if isinstance(extracted, dict) else {}, plan),
                    "stop": plan.get("stop"),
                    "target1": plan.get("target1"),
                    "target2": plan.get("target2"),
                    "target3": plan.get("target3"),
                    "geometry_valid": bool(geometry.get("valid")),
                    "plan_id": fields["plan_id"],
                    "report": report,
                }
            )
    st.session_state["signals_v4_cache"] = cache
    return rows


def _render_summary(rows: list[dict[str, Any]]) -> None:
    actionable = sum(row["lifecycle"] == "ACTIONABLE" for row in rows)
    heads_up = sum(row["lifecycle"] == "HEADS_UP" for row in rows)
    blocked = sum(row["lifecycle"] == "BLOCKED" for row in rows)
    valid_plans = sum(bool(row["geometry_valid"]) for row in rows)
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("دخول مؤكد", actionable, "success", "✅")
    with c2:
        render_kpi("قرب الدخول", heads_up, "warning", "👀")
    with c3:
        render_kpi("محظورة", blocked, "danger", "⛔")
    with c4:
        render_kpi("خطط سليمة", valid_plans, "blue", "🛡️")


def _display_rows(rows: list[dict[str, Any]]) -> None:
    if not rows:
        st.info("لا توجد نتائج.")
        return
    display = pd.DataFrame(
        [
            {
                "الرمز": row["symbol"],
                "الفاصل": TIMEFRAMES.get(row["timeframe"], row["timeframe"]),
                "المرحلة": row["stage"],
                "الاتجاه": "صاعد" if row["direction"] == "buy" else "هابط" if row["direction"] == "sell" else "محايد",
                "الفرصة": row["opportunity"],
                "الثقة %": row["confidence"],
                "المدارس": row["schools"],
                "أسماء المدارس": row["school_names"] or "—",
                "الدخول": row["entry"],
                "الوقف": row["stop"],
                "T1": row["target1"],
                "T2": row["target2"],
                "T3": row["target3"],
                "الخطة": "صالحة" if row["geometry_valid"] else "غير مكتملة",
            }
            for row in rows
        ]
    )
    render_custom_table(display)

    actionable_rows = [row for row in rows if row["lifecycle"] in {"ACTIONABLE", "HEADS_UP", "BLOCKED"}]
    for row in actionable_rows:
        with st.expander(f"{row['symbol']} — {TIMEFRAMES.get(row['timeframe'])} — {row['stage']}", expanded=False):
            report = row["report"]
            left, right = st.columns(2)
            with left:
                st.markdown("**الأدلة:**")
                for item in (report.get("top_evidence") or [])[:6]:
                    st.write(f"- {item}")
            with right:
                st.markdown("**المخاطر:**")
                for item in (report.get("top_risks") or [])[:6]:
                    st.write(f"- {item}")
            st.caption(f"رقم الخطة: {row['plan_id'] or '—'} — لا يوجد تنفيذ أوامر من التطبيق.")


def view_signals(finance: dict[str, Any] | None = None) -> None:
    finance = finance or {}
    st.header("🚦 مركز الإشارات")
    st.caption("مسح صريح للمحفظة من الدقيقة إلى الشهري. لا يعمل تلقائيًا عند فتح الصفحة أو إعادة رسمها.")
    universe = _symbol_universe(finance)
    if not universe:
        st.info("أضف مركز سهم مفتوح أولًا، أو استخدم النظرة الموحدة لتحليل رمز منفرد.")
        return
    selected_symbols = st.multiselect(
        "الأسهم",
        universe,
        default=universe[: min(8, len(universe))],
        key="رموز مركز الإشارات",
    )
    selected_frames = st.multiselect(
        "الفواصل",
        options=list(TIMEFRAMES),
        default=["15m", "1h", "4h", "1d", "1wk"],
        format_func=lambda value: TIMEFRAMES[value],
        key="فواصل مركز الإشارات",
    )
    c1, c2 = st.columns([3, 1])
    run = c1.button(
        "تشغيل مسح الإشارات",
        type="primary",
        use_container_width=True,
        key="تشغيل مركز الإشارات",
    )
    refresh = c2.button(
        "إعادة الحساب",
        use_container_width=True,
        key="تحديث مركز الإشارات",
    )
    if run or refresh:
        if not selected_symbols or not selected_frames:
            st.warning("اختر سهمًا وفاصلًا واحدًا على الأقل.")
        else:
            with st.spinner("جاري تحليل الفواصل وتدقيق المدارس والخطط..."):
                st.session_state["signals_v4_rows"] = _run(selected_symbols, selected_frames, refresh=refresh)
    rows = st.session_state.get("signals_v4_rows") or []
    if not rows:
        st.info("حدد النطاق واضغط «تشغيل مسح الإشارات».")
        return
    lifecycle_filter = st.multiselect(
        "عرض الحالات",
        ["ACTIONABLE", "HEADS_UP", "BLOCKED", "NO_SETUP"],
        default=["ACTIONABLE", "HEADS_UP", "BLOCKED"],
        key="حالات مركز الإشارات",
    )
    filtered = [row for row in rows if row["lifecycle"] in lifecycle_filter]
    _render_summary(rows)
    _display_rows(filtered)
