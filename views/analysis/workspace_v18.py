"""Practical two-mode analysis workspace for ordinary investors.

The engine remains unchanged. This module turns its structured report into:
1. a bot-like directional plan with entry, stop and targets; and
2. a portfolio-aware advisor that states the next action, position size and
   conditions that would change the decision.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import streamlit as st

from components import render_custom_table, render_kpi
from views.shared import _generate_ai_report_flex, _sym_key
from views.utils import normalize_symbol, safe_status_series

MODE_ANALYSIS = "📊 التحليل والصفقة"
MODE_ADVISOR = "🧠 المستشار"


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _items(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple)):
        return list(value)
    return []


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _positive(value: Any) -> float | None:
    result = _number(value)
    return result if result is not None and result > 0 else None


def _price(value: Any) -> str:
    number = _positive(value)
    if number is None:
        return "—"
    return f"{number:,.4f}".rstrip("0").rstrip(".")


def _percent(value: Any) -> str:
    number = _number(value)
    return "—" if number is None else f"{number:.0f}%"


def _cache() -> dict[str, dict[str, Any]]:
    value = st.session_state.get("analysis_workspace_v18_cache")
    if not isinstance(value, dict):
        value = {}
        st.session_state["analysis_workspace_v18_cache"] = value
    return value


def _cache_key(symbol: str, interval: str) -> str:
    return f"{normalize_symbol(symbol)}|{interval}"


def _generate(
    symbol: str,
    interval: str,
    *,
    refresh: bool = False,
) -> dict[str, Any]:
    cache = _cache()
    key = _cache_key(symbol, interval)
    if refresh:
        cache.pop(key, None)
    if key not in cache:
        cache[key] = {
            "report": _generate_ai_report_flex(symbol, timeframe=interval),
            "generated_at": datetime.now(timezone.utc)
            .replace(microsecond=0)
            .isoformat(),
        }
        st.session_state["analysis_workspace_v18_cache"] = cache
    return _mapping(cache.get(key))


def _direction_code(value: Any) -> int:
    text = str(value or "").strip().lower()
    if value == 1 or text in {"1", "buy", "long", "bullish", "صاعد"}:
        return 1
    if value == -1 or text in {"-1", "sell", "short", "bearish", "هابط"}:
        return -1
    return 0


def _direction_text(value: Any) -> str:
    direction = _direction_code(value)
    if direction > 0:
        return "صاعد"
    if direction < 0:
        return "هابط"
    return "محايد"


def _plan(report: dict[str, Any]) -> dict[str, Any]:
    direct = _mapping(report.get("risk_plan"))
    if direct.get("entry") is not None:
        return direct
    pack = _mapping(report.get("sc_feature_pack"))
    return _mapping(pack.get("risk_plan"))


def _targets(plan: dict[str, Any]) -> list[float]:
    values: list[Any] = []
    listed = _items(plan.get("targets"))
    if listed:
        values.extend(listed)
    else:
        values.extend(
            [
                plan.get("target1"),
                plan.get("target2"),
                plan.get("target3"),
            ]
        )
    output: list[float] = []
    for value in values:
        number = _positive(value)
        if number is not None and number not in output:
            output.append(number)
    return output[:3]


def _levels(report: dict[str, Any]) -> tuple[float | None, float | None]:
    pack = _mapping(report.get("sc_feature_pack"))
    sr = _mapping(pack.get("sr"))
    support = _mapping(sr.get("support"))
    resistance = _mapping(sr.get("resistance"))
    features = _mapping(report.get("features"))
    support_value = (
        _positive(support.get("level"))
        or _positive(features.get("sc_support_cluster"))
        or _positive(report.get("support"))
    )
    resistance_value = (
        _positive(resistance.get("level"))
        or _positive(features.get("sc_resistance_cluster"))
        or _positive(report.get("resistance"))
    )
    return support_value, resistance_value


def _closed_price(report: dict[str, Any]) -> float | None:
    meta = _mapping(report.get("engine_meta"))
    frame = _mapping(report.get("frame"))
    return (
        _positive(report.get("closed_candle_price"))
        or _positive(frame.get("closed_candle_price"))
        or _positive(frame.get("price"))
        or _positive(meta.get("closed_candle_price"))
        or _positive(report.get("price"))
    )


def _live_context(report: dict[str, Any]) -> dict[str, Any]:
    return _mapping(report.get("live_quote_context"))


def _report_error(report: dict[str, Any]) -> str | None:
    if not report:
        return None
    status = str(report.get("status") or "").strip().lower()
    if report.get("__error__") or status == "error" or report.get("ok") is False:
        return str(report.get("message") or "تعذر إكمال التحليل بأمان.")
    return None


def _is_actionable(report: dict[str, Any], plan: dict[str, Any]) -> bool:
    lifecycle = str(report.get("lifecycle_status") or "").strip().upper()
    geometry = _mapping(report.get("plan_geometry"))
    if lifecycle == "ACTIONABLE":
        return bool(
            _positive(plan.get("entry"))
            and _positive(plan.get("stop"))
            and _targets(plan)
        )
    return bool(
        report.get("plan_valid")
        and geometry.get("valid", True)
        and _positive(plan.get("entry"))
        and _positive(plan.get("stop"))
        and _targets(plan)
    )


def _decision(report: dict[str, Any]) -> dict[str, Any]:
    plan = _plan(report)
    direction = _direction_code(
        report.get("direction")
        or _mapping(report.get("sc_feature_pack")).get("direction")
    )
    lifecycle = str(report.get("lifecycle_status") or "NO_SETUP").upper()
    actionable = _is_actionable(report, plan) and direction != 0
    if actionable and direction > 0:
        title = "فرصة صعود مؤهلة"
        action = "دخول صاعد مشروط"
        tone = "success"
        icon = "📈"
    elif actionable and direction < 0:
        title = "فرصة هبوط مؤهلة"
        action = "دخول هابط مشروط"
        tone = "danger"
        icon = "📉"
    elif lifecycle == "BLOCKED":
        title = "الدخول مرفوض حاليًا"
        action = "تجنب الدخول"
        tone = "danger"
        icon = "⛔"
    elif lifecycle == "HEADS_UP" or direction != 0:
        title = "اتجاه موجود لكن التفعيل ناقص"
        action = "مراقبة شرط التفعيل"
        tone = "warning"
        icon = "👀"
    else:
        title = "لا توجد صفقة واضحة الآن"
        action = "مراقبة"
        tone = "neutral"
        icon = "⏸️"
    return {
        "title": title,
        "action": action,
        "tone": tone,
        "icon": icon,
        "direction": direction,
        "actionable": actionable,
        "lifecycle": lifecycle,
        "plan": plan,
    }


def _confidence(report: dict[str, Any]) -> float:
    value = _number(report.get("confidence"))
    if value is None:
        value = _number(_mapping(report.get("sc_feature_pack")).get("confidence"))
    return max(0.0, min(100.0, value or 0.0))


def _data_score(report: dict[str, Any]) -> float:
    reliability = _mapping(report.get("data_reliability"))
    value = _number(reliability.get("score"))
    return max(0.0, min(100.0, value or 0.0))


def _evidence(report: dict[str, Any]) -> list[str]:
    values = [str(item).strip() for item in _items(report.get("top_evidence"))]
    if not values:
        values = [str(item).strip() for item in _items(report.get("reasons"))]
    return [item for item in values if item][:5]


def _risks(report: dict[str, Any]) -> list[str]:
    values = [str(item).strip() for item in _items(report.get("top_risks"))]
    if not values:
        pack = _mapping(report.get("sc_feature_pack"))
        values = [str(item).strip() for item in _items(pack.get("warnings"))]
    geometry = _mapping(report.get("plan_geometry"))
    values.extend(str(item).strip() for item in _items(geometry.get("issues")))
    output: list[str] = []
    for value in values:
        if value and value not in output:
            output.append(value)
    return output[:5]


def _position_context(
    symbol: str,
    finance: dict[str, Any],
) -> dict[str, Any]:
    trades = finance.get("all_trades")
    if not isinstance(trades, pd.DataFrame) or trades.empty:
        return {"has_position": False}
    frame = trades.copy()
    if "symbol" not in frame.columns:
        return {"has_position": False}
    normalized = frame["symbol"].fillna("").astype(str).map(normalize_symbol)
    status = safe_status_series(frame)
    matches = frame[(normalized == normalize_symbol(symbol)) & (status == "open")]
    if matches.empty:
        return {"has_position": False}
    quantity = pd.to_numeric(
        matches.get("quantity", pd.Series(0.0, index=matches.index)),
        errors="coerce",
    ).fillna(0.0)
    entry = pd.to_numeric(
        matches.get("entry_price", pd.Series(0.0, index=matches.index)),
        errors="coerce",
    ).fillna(0.0)
    total_quantity = float(quantity.sum())
    total_cost = float((quantity * entry).sum())
    average_entry = total_cost / total_quantity if total_quantity > 0 else None
    return {
        "has_position": total_quantity > 0,
        "quantity": total_quantity,
        "average_entry": average_entry,
        "positions": int(len(matches)),
    }


def _portfolio_value(finance: dict[str, Any]) -> float | None:
    value = _positive(finance.get("portfolio_value"))
    if value is not None:
        return value
    trades = finance.get("all_trades")
    if not isinstance(trades, pd.DataFrame) or trades.empty:
        return None
    status = safe_status_series(trades)
    frame = trades[status == "open"].copy()
    if frame.empty:
        return None
    quantity = pd.to_numeric(
        frame.get("quantity", pd.Series(0.0, index=frame.index)),
        errors="coerce",
    ).fillna(0.0)
    current = pd.to_numeric(
        frame.get(
            "current_price",
            frame.get("entry_price", pd.Series(0.0, index=frame.index)),
        ),
        errors="coerce",
    ).fillna(0.0)
    total = float((quantity * current).sum())
    return total if total > 0 else None


def _position_size(
    report: dict[str, Any],
    finance: dict[str, Any],
) -> dict[str, Any]:
    decision = _decision(report)
    plan = decision["plan"]
    entry = _positive(plan.get("entry"))
    stop = _positive(plan.get("stop"))
    portfolio = _portfolio_value(finance)
    if not decision["actionable"] or not entry or not stop or not portfolio:
        return {}
    risk_per_unit = abs(entry - stop)
    if risk_per_unit <= 0:
        return {}
    risk_budget = portfolio * 0.01
    by_risk = math.floor(risk_budget / risk_per_unit)
    by_concentration = math.floor((portfolio * 0.20) / entry)
    units = max(0, min(by_risk, by_concentration))
    return {
        "units": units,
        "risk_budget": risk_budget,
        "risk_per_unit": risk_per_unit,
        "position_value": units * entry,
        "portfolio": portfolio,
    }


def _render_decision_header(report: dict[str, Any]) -> None:
    decision = _decision(report)
    consensus = _mapping(report.get("school_consensus"))
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi(
            "القرار الآن",
            decision["action"],
            decision["tone"],
            decision["icon"],
        )
    with c2:
        render_kpi(
            "الاتجاه",
            _direction_text(decision["direction"]),
            decision["tone"],
            "↕️",
        )
    with c3:
        render_kpi("الثقة", _percent(_confidence(report)), "blue", "🎯")
    with c4:
        render_kpi(
            "توافق المدارس",
            str(int(consensus.get("school_count") or 0)),
            "neutral",
            "🏫",
        )
    st.subheader(f"{decision['icon']} {decision['title']}")
    recommendation = str(report.get("recommendation") or "").strip()
    strategy = str(report.get("strategy") or "").strip()
    if recommendation:
        st.write(recommendation)
    if strategy and strategy != recommendation:
        st.caption(strategy)


def _render_prices(report: dict[str, Any]) -> None:
    closed = _closed_price(report)
    live = _live_context(report)
    live_price = _positive(live.get("price"))
    left, right = st.columns(2)
    left.metric("إغلاق الشمعة المعتمد", _price(closed))
    right.metric(
        "السعر السياقي الآن",
        _price(live_price),
        help="للعرض فقط؛ لا يغير الاتجاه أو الدخول أو الوقف أو الأهداف.",
    )
    source = str(live.get("source") or "غير متاح")
    if live_price is not None:
        st.caption(
            f"السعر السياقي من {source} ولا يدخل في حساب الإشارة أو الخطة."
        )


def _render_plan(report: dict[str, Any]) -> None:
    decision = _decision(report)
    plan = decision["plan"]
    entry = _positive(plan.get("entry"))
    stop = _positive(plan.get("stop"))
    targets = _targets(plan)
    support, resistance = _levels(report)

    st.markdown("### الخطة العملية")
    if not decision["actionable"]:
        st.info(
            "لا يوجد دخول مؤهل على آخر شمعة مكتملة. راقب المستويات ولا تنشئ "
            "صفقة قبل ظهور زناد صالح."
        )
        c1, c2 = st.columns(2)
        c1.metric("الدعم الأقرب", _price(support))
        c2.metric("المقاومة الأقرب", _price(resistance))
        return

    values = [
        ("الدخول", entry),
        ("الوقف", stop),
        ("الهدف 1", targets[0] if len(targets) > 0 else None),
        ("الهدف 2", targets[1] if len(targets) > 1 else None),
        ("الهدف 3", targets[2] if len(targets) > 2 else None),
    ]
    columns = st.columns(5)
    for column, (label, value) in zip(columns, values, strict=False):
        column.metric(label, _price(value))

    geometry = _mapping(report.get("plan_geometry"))
    ratios = _items(geometry.get("target_r"))
    ratio_text = " | ".join(
        f"T{index + 1}={float(value):.2f}R"
        for index, value in enumerate(ratios)
        if _number(value) is not None
    )
    if ratio_text:
        st.caption(ratio_text)
    invalidation = str(
        plan.get("invalidation")
        or plan.get("invalidation_rule")
        or "إغلاق يتجاوز الوقف البنيوي"
    )
    st.write(f"**إلغاء الفكرة:** {invalidation}")
    st.caption(
        "لا تطارد السعر بعيدًا عن الدخول. الوقف الفني والكسر الحقيقي يعتمدان "
        "على إغلاق الشمعة حسب عقد المحرك."
    )


def _render_scenarios(report: dict[str, Any]) -> None:
    decision = _decision(report)
    support, resistance = _levels(report)
    plan = decision["plan"]
    entry = _positive(plan.get("entry"))
    stop = _positive(plan.get("stop"))
    targets = _targets(plan)

    st.markdown("### سيناريو الصعود والهبوط")
    up, down = st.columns(2)
    with up:
        st.markdown("#### 📈 الصعود")
        if decision["actionable"] and decision["direction"] > 0:
            st.success(
                f"يتفعّل قرب {_price(entry)}، والهدف الأول {_price(targets[0])}."
            )
        elif resistance:
            st.write(
                f"راقب إغلاقًا مؤكدًا فوق المقاومة {_price(resistance)} قبل "
                "اعتبار الصعود قابلًا للتنفيذ."
            )
        else:
            st.write("لا يوجد زناد صعود مؤهل حاليًا.")
    with down:
        st.markdown("#### 📉 الهبوط")
        if decision["actionable"] and decision["direction"] < 0:
            st.error(
                f"يتفعّل قرب {_price(entry)}، والهدف الأول {_price(targets[0])}."
            )
        elif support:
            st.write(
                f"كسر الدعم {_price(support)} بإغلاق يرفع احتمال استمرار الهبوط."
            )
        else:
            st.write("لا يوجد زناد هبوط مؤهل حاليًا.")
    if stop:
        st.caption(f"الحد البنيوي الذي يبطل الخطة الحالية: {_price(stop)}")


def _advisor_action(
    report: dict[str, Any],
    finance: dict[str, Any],
    symbol: str,
) -> dict[str, Any]:
    decision = _decision(report)
    position = _position_context(symbol, finance)
    plan = decision["plan"]
    entry = _positive(plan.get("entry"))
    stop = _positive(plan.get("stop"))
    targets = _targets(plan)

    if position.get("has_position"):
        if decision["actionable"] and decision["direction"] > 0:
            title = "احتفاظ مشروط — لا تعزز عشوائيًا"
            steps = [
                "احتفظ ما دام الإغلاق لم يكسر مستوى الإبطال.",
                f"التعزيز فقط قرب دخول الخطة {_price(entry)} وبعد بقاء التفعيل صالحًا.",
                f"خفف جزءًا عند الهدف الأول {_price(targets[0])} وفق خطتك.",
            ]
        elif decision["direction"] < 0:
            title = "احمِ المركز أو خفف المخاطرة"
            steps = [
                "الاتجاه الحالي يعارض المركز المفتوح؛ لا تضف كمية جديدة.",
                f"راجع الخروج إذا أغلقت الشمعة بعد مستوى الإبطال {_price(stop)}.",
                "تجنب تحويل الصفقة القصيرة الأجل إلى استثمار بلا خطة.",
            ]
        else:
            title = "احتفاظ مراقب بلا تعزيز"
            steps = [
                "لا توجد إشارة تنفيذية جديدة تبرر زيادة المركز.",
                f"راقب الإبطال البنيوي {_price(stop)} والمقاومة قبل أي قرار.",
                "خفف المخاطرة إذا تجاوز حجم المركز حدود محفظتك.",
            ]
    elif decision["actionable"]:
        direction_text = "صاعدة" if decision["direction"] > 0 else "هابطة"
        title = f"فرصة {direction_text} — تنفيذ منضبط فقط"
        steps = [
            f"الدخول قرب {_price(entry)} فقط، ولا تطارد الحركة.",
            f"الوقف {_price(stop)} والهدف الأول {_price(targets[0])}.",
            "لا تنفذ إن تغيرت هندسة الخطة أو انتهت صلاحيتها قبل الدخول.",
        ]
    else:
        title = "لا تدخل الآن"
        support, resistance = _levels(report)
        steps = [
            "القرار الحالي للمراقبة وليس صفقة مكتملة.",
            f"راقب المقاومة {_price(resistance)} والدعم {_price(support)}.",
            "انتظر إغلاقًا مؤكدًا وخطة بوقف وأهداف قبل المخاطرة.",
        ]
    return {"title": title, "steps": steps, "position": position}


def _render_advisor(
    report: dict[str, Any],
    finance: dict[str, Any],
    symbol: str,
) -> None:
    advice = _advisor_action(report, finance, symbol)
    position = advice["position"]
    st.subheader(f"🧠 قرار المستشار: {advice['title']}")

    if position.get("has_position"):
        c1, c2, c3 = st.columns(3)
        c1.metric("لديك مركز", "نعم")
        c2.metric("الكمية", f"{float(position.get('quantity') or 0):,.2f}")
        c3.metric("متوسط الدخول", _price(position.get("average_entry")))
    else:
        st.caption("لا يوجد مركز مفتوح لهذا الرمز في المحفظة الحالية.")

    st.markdown("### ماذا تفعل الآن؟")
    for index, step in enumerate(advice["steps"], start=1):
        st.write(f"**{index}.** {step}")

    size = _position_size(report, finance)
    if size:
        st.markdown("### حجم مقترح محافظ")
        c1, c2, c3 = st.columns(3)
        c1.metric("الكمية القصوى", f"{int(size['units']):,}")
        c2.metric("مخاطرة الخطة", f"{size['risk_budget']:,.2f}")
        c3.metric("قيمة المركز", f"{size['position_value']:,.2f}")
        st.caption(
            "الحساب يستخدم مخاطرة 1% من قيمة المحفظة وحد تركّز 20%. "
            "هو سقف تقديري وليس أمر شراء أو بيع."
        )

    plan = _plan(report)
    stop = _positive(plan.get("stop"))
    expiry = plan.get("expiry_bars")
    st.markdown("### متى يتغير رأي المستشار؟")
    changes = [
        f"إغلاق يتجاوز مستوى الإبطال أو الوقف {_price(stop)}.",
        "ظهور إشارة معاكسة مؤهلة من عائلتين مستقلتين.",
    ]
    if expiry:
        changes.append(f"انتهاء صلاحية الخطة بعد {expiry} شمعة دون تفعيل أو تقدم.")
    for item in changes:
        st.write(f"- {item}")

    risks = _risks(report)
    if risks:
        st.markdown("### ما الذي يمنع التنفيذ؟")
        for item in risks[:3]:
            st.write(f"- {item}")


def _render_advanced(report: dict[str, Any]) -> None:
    with st.expander("⚙️ التفاصيل المتقدمة والمصادر", expanded=False):
        evidence = _evidence(report)
        risks = _risks(report)
        left, right = st.columns(2)
        with left:
            st.markdown("#### أقوى الأدلة")
            for item in evidence or ["لا توجد أدلة إضافية محفوظة."]:
                st.write(f"- {item}")
        with right:
            st.markdown("#### المخاطر والموانع")
            for item in risks or ["لا توجد موانع إضافية محفوظة."]:
                st.write(f"- {item}")

        consensus = _mapping(report.get("school_consensus"))
        rows = []
        for item in _items(consensus.get("signals")):
            signal = _mapping(item)
            rows.append(
                {
                    "المدرسة": signal.get("school"),
                    "المحور": signal.get("axis"),
                    "الاتجاه": _direction_text(signal.get("direction")),
                    "القوة": signal.get("strength"),
                    "تنفيذي": bool(signal.get("actionable")),
                    "السبب": signal.get("reason"),
                }
            )
        if rows:
            st.markdown("#### المدارس الفنية")
            render_custom_table(pd.DataFrame(rows))

        reliability = _mapping(report.get("data_reliability"))
        meta = _mapping(report.get("engine_meta"))
        lineage = _mapping(meta.get("data_lineage"))
        live = _live_context(report)
        source_rows = [
            {
                "الطبقة": "الشموع المكتملة",
                "المصدر": reliability.get("price_source")
                or lineage.get("source")
                or "غير معروف",
                "الحالة": "يبني القرار",
            },
            {
                "الطبقة": "السعر السياقي",
                "المصدر": live.get("source") or "غير متاح",
                "الحالة": "للعرض فقط",
            },
            {
                "الطبقة": "القوائم المالية",
                "المصدر": reliability.get("financial_source") or "غير متاح",
                "الحالة": "سياق أساسي",
            },
        ]
        st.markdown("#### مصادر القرار")
        render_custom_table(pd.DataFrame(source_rows))
        contract = _mapping(report.get("analysis_contract"))
        st.caption(
            f"عقد المؤشر: {contract.get('indicator_contract', '—')} — "
            f"إصدار القرار: {contract.get('decision_version', '—')} — "
            f"آخر شمعة: {meta.get('last_bar', '—')}"
        )


def render_decision_workspace(
    symbol: str,
    interval: str,
    finance: dict[str, Any] | None = None,
) -> None:
    """Render one report through two simple user-facing modes."""
    finance = finance or {}
    st.subheader("تحليل واضح بقرار واحد")
    st.caption(
        "المحرك يحلل الصعود والهبوط من الشموع المكتملة، ثم يعرض الدخول "
        "والوقف والأهداف عند اكتمال الشروط."
    )

    run_col, refresh_col = st.columns([3, 1])
    run = run_col.button(
        "حلل الآن",
        type="primary",
        use_container_width=True,
        key=f"workspace_v18_run:{_sym_key(symbol)}:{interval}",
    )
    refresh = refresh_col.button(
        "تحديث",
        use_container_width=True,
        key=f"workspace_v18_refresh:{_sym_key(symbol)}:{interval}",
    )
    if run or refresh:
        with st.spinner("جاري تحليل الاتجاه والخطة والمخاطر..."):
            _generate(symbol, interval, refresh=refresh)

    payload = _mapping(_cache().get(_cache_key(symbol, interval)))
    report = _mapping(payload.get("report"))
    if not report:
        st.info("اضغط «حلل الآن» لعرض الاتجاه والخطة والمستشار.")
        return
    error = _report_error(report)
    if error:
        st.error(error)
        return

    mode = st.radio(
        "طريقة العرض",
        [MODE_ANALYSIS, MODE_ADVISOR],
        horizontal=True,
        label_visibility="collapsed",
        key=f"workspace_v18_mode:{_sym_key(symbol)}",
    )
    _render_decision_header(report)
    _render_prices(report)
    if mode == MODE_ANALYSIS:
        _render_plan(report)
        _render_scenarios(report)
    else:
        _render_advisor(report, finance, symbol)
    _render_advanced(report)
    st.caption(
        f"آخر تحليل: {payload.get('generated_at', '—')} — النتيجة تعليمية "
        "ولا تضمن الربح."
    )


__all__ = ["render_decision_workspace"]
