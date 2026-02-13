# views/analysis/technical.py
# -*- coding: utf-8 -*-

"""واجهة التحليل الفني.

مهم:
- لا يتم حذف أي شيء من الواجهة الحالية.
- تمت إضافة قسم "مؤشرات متقدمة" فقط كإضافة.
- هذه المؤشرات (عند توفرها) يتم استخدام نفس نتائجها داخل المستشار (AI)
  عبر ai_engine_core/packs.py.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import math

import pandas as pd
import streamlit as st

from components import render_custom_table

from market_data import get_chart_history
from views.shared import _render_technical_chart_flex

# ==============================
# مؤشرات متقدمة (Advanced Indicators)
# ==============================
# هذا الاستيراد اختياري حتى لا ينكسر التطبيق إذا لم تكن الحزمة موجودة.
_ADV_AVAILABLE = True
try:
    from technical_indicators.advanced import compute_advanced_technical_pack
except Exception:
    compute_advanced_technical_pack = None
    _ADV_AVAILABLE = False


def _as_list(x: Any) -> List[Any]:
    if x is None:
        return []
    if isinstance(x, list):
        return x
    return [x]


def _safe_int(x: Any, default: Optional[int] = None) -> Optional[int]:
    try:
        if x is None:
            return default
        return int(float(x))
    except Exception:
        return default


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _format_pct(x: Any) -> str:
    v = _safe_int(x, None)
    if v is None:
        return "—"
    return f"{_clamp(v, 0, 100):.0f}%"


def _bias_label(bias: Any) -> Tuple[str, str]:
    """ترميز بسيط للاتجاه/التحيز."""
    if bias is None:
        return ("محايد", "⚪")

    # رقم
    if isinstance(bias, (int, float)):
        try:
            fv = float(bias)
            if math.isnan(fv):
                return ("محايد", "⚪")
            if fv > 0:
                return ("إيجابي", "🟢")
            if fv < 0:
                return ("سلبي", "🔴")
            return ("محايد", "⚪")
        except Exception:
            return (str(bias), "⚪")

    s = str(bias).strip().lower()
    if s in ("bullish", "up", "long", "positive", "buy"):
        return ("إيجابي", "🟢")
    if s in ("bearish", "down", "short", "negative", "sell"):
        return ("سلبي", "🔴")
    if s in ("neutral", "side", "range", "hold"):
        return ("محايد", "⚪")
    return (str(bias), "⚪")


def _df_quality_snapshot(df: pd.DataFrame) -> Dict[str, Any]:
    """فحص سريع لجودة بيانات OHLCV المستخدمة في المؤشرات المتقدمة."""
    out: Dict[str, Any] = {"ok": True, "issues": [], "candles": 0, "last_dt": None}

    if df is None or df.empty:
        out["ok"] = False
        out["issues"].append("لا توجد بيانات سعرية.")
        return out

    out["candles"] = int(len(df))
    try:
        out["last_dt"] = str(df.index[-1])
    except Exception:
        pass

    # متطلبات دنيا (مبدئية)
    if len(df) < 220:
        out["issues"].append("عدد الشموع أقل من 220 (قد يضعف دقة مؤشرات مثل MA200/ADX/نماذج الاتجاه).")

    required = {"Open", "High", "Low", "Close"}
    missing_cols = [c for c in required if c not in df.columns]
    if missing_cols:
        out["ok"] = False
        out["issues"].append(f"أعمدة ناقصة: {', '.join(missing_cols)}")

    # تحقق من قيم غير منطقية
    try:
        if "High" in df.columns and "Low" in df.columns:
            bad = int((df["High"] < df["Low"]).sum())
            if bad:
                out["issues"].append(f"وجدت {bad} شموع فيها High < Low (بيانات غير منطقية).")
    except Exception:
        pass

    out["ok"] = bool(out["ok"] and (len(out["issues"]) == 0))
    return out


def _render_quality_badge(df: pd.DataFrame):
    q = _df_quality_snapshot(df)

    col1, col2, col3 = st.columns([1.2, 1.2, 2.6])
    with col1:
        st.metric("عدد الشموع", q.get("candles", 0))
    with col2:
        st.metric("آخر شمعة", q.get("last_dt") or "—")
    with col3:
        if q["ok"]:
            st.success("جودة البيانات: **جيدة** ✅")
        else:
            st.warning("جودة البيانات: **تحتاج انتباه** ⚠️")

    if q.get("issues"):
        with st.expander("تفاصيل جودة البيانات (لماذا قد تقل الدقة؟)"):
            st.write("\n".join([f"- {x}" for x in q["issues"]]))



def _render_table_like_trades(df: pd.DataFrame, columns_config, *, key: str):
    """عرض جدول بنفس ستايل جدول الصفقات (finance-table)."""
    try:
        render_custom_table(df, columns_config=columns_config, key=key, width="stretch")
    except Exception:
        st.dataframe(df, width="stretch", hide_index=True)


def _render_signals_table(signals: List[Any], title: str = "الإشارات"):
    if not signals:
        st.caption("لا توجد إشارات مُهيكلة من هذا المؤشر.")
        return

    norm: List[Dict[str, Any]] = []
    for s in signals:
        if isinstance(s, dict):
            norm.append(s)
        else:
            norm.append({"signal": str(s)})

    df_sig = pd.DataFrame(norm)

    preferred = [c for c in ["signal", "name", "type", "direction", "score", "strength", "note", "when"] if c in df_sig.columns]
    rest = [c for c in df_sig.columns if c not in preferred]
    df_sig = df_sig[preferred + rest]

    col_map = {
        "signal": "الإشارة",
        "name": "الاسم",
        "type": "النوع",
        "direction": "الاتجاه",
        "score": "الدرجة",
        "strength": "القوة",
        "note": "ملاحظة",
        "when": "التوقيت",
    }

    columns_config = []
    for c in df_sig.columns:
        label = col_map.get(c, c)
        col_type = "auto"
        if c in ("score", "strength"):
            col_type = "number"
        columns_config.append((c, label, col_type))

    st.markdown(f"**{title}:**")
    _render_table_like_trades(df_sig, columns_config, key=f"adv_sig_{abs(hash(title)) % 100000}")



def _render_features_table(features: Dict[str, Any]):
    if not isinstance(features, dict) or not features:
        st.caption("لا توجد خصائص (Features) مُهيكلة.")
        return

    rows = [{"feature": str(k), "value": v} for k, v in features.items()]
    df_feat = pd.DataFrame(rows)

    columns_config = [
        ("feature", "البند", "text"),
        ("value", "القيمة", "auto"),
    ]
    _render_table_like_trades(df_feat, columns_config, key=f"adv_feat_{len(df_feat)}")



def _render_indicator_block(title: str, res: Dict[str, Any]):
    """عرض موحد للمؤشر: تحيز + ثقة + رأي + أدلة + إشارات + Features."""
    if not isinstance(res, dict):
        st.error(f"{title}: نتيجة غير صالحة (ليست dict).")
        return

    conf = res.get("confidence")
    bias = res.get("bias") or res.get("trend") or res.get("direction")
    summary = res.get("summary") or res.get("opinion") or res.get("commentary")

    bias_txt, bias_icon = _bias_label(bias)

    st.markdown(f"### {title}")
    c1, c2, c3 = st.columns([1.2, 1.2, 2.6])
    with c1:
        st.metric("التحيز", f"{bias_icon} {bias_txt}")
    with c2:
        st.metric("الثقة", _format_pct(conf))
    with c3:
        if summary:
            st.info(f"**الرأي المختصر:** {summary}")
        else:
            st.caption("الرأي المختصر: —")

    errors = _as_list(res.get("errors")) + _as_list(res.get("warnings"))
    if errors:
        with st.expander("ملاحظات/أخطاء أثناء الحساب"):
            st.write("\n".join([f"- {e}" for e in errors]))

    evidence = _as_list(res.get("evidence"))
    if evidence:
        with st.expander("الأدلة التي بنى عليها المؤشر حكمه"):
            st.write("\n".join([f"- {e}" for e in evidence]))

    signals = _as_list(res.get("signals"))
    if signals:
        _render_signals_table(signals, title="إشارات المؤشر")

    features = res.get("features", {})
    if isinstance(features, dict) and features:
        with st.expander("خصائص/Features (تفاصيل رقمية)"):
            _render_features_table(features)


def _pack_items(pack: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for k in ["rls_forecast", "chaos_wrsi", "volume_profile_clusters", "trendline_breakout"]:
        v = pack.get(k)
        if isinstance(v, dict) and v:
            items.append(v)
    return items


def _pack_score(pack: Dict[str, Any]) -> Tuple[int, int, str]:
    """ملخص الاتجاه العام: متوسط الثقة + صافي الميل + وصف."""
    items = _pack_items(pack)
    if not items:
        return (0, 0, "لا توجد نتائج.")

    confs: List[float] = []
    pos = 0
    neg = 0

    for it in items:
        c = _safe_int(it.get("confidence"), None)
        if c is not None:
            confs.append(_clamp(float(c), 0, 100))

        btxt, _ = _bias_label(it.get("bias") or it.get("trend") or it.get("direction"))
        if btxt == "إيجابي":
            pos += 1
        elif btxt == "سلبي":
            neg += 1

    avg_conf = int(round(sum(confs) / max(1, len(confs)))) if confs else 0
    tilt = pos - neg

    if pos > neg:
        overall = "الغالب: **إيجابي**"
    elif neg > pos:
        overall = "الغالب: **سلبي**"
    else:
        overall = "الغالب: **محايد/مختلط**"

    return (avg_conf, tilt, overall)


def _advanced_unified_score(pack: Dict[str, Any], df: pd.DataFrame) -> Tuple[int, List[str]]:
    """Score موحد (0-100) للمؤشرات المتقدمة + تفسير."""
    explain: List[str] = []

    items = _pack_items(pack)
    if not items:
        return 0, ["لا توجد نتائج صالحة لحساب الدرجة."]

    avg_conf, tilt, overall = _pack_score(pack)

    # Base
    score = float(avg_conf)
    explain.append(f"الأساس = متوسط الثقة عبر المؤشرات = **{avg_conf}%**")

    # Agreement bonus (المؤشرات متفقة)
    abs_tilt = abs(int(tilt))
    if abs_tilt >= 3:
        score += 8
        explain.append("اتفاق قوي بين المؤشرات (ميل ≥ 3): **+8**")
    elif abs_tilt == 2:
        score += 5
        explain.append("اتفاق جيد بين المؤشرات (ميل = 2): **+5**")
    elif abs_tilt == 1:
        score += 2
        explain.append("اتفاق بسيط بين المؤشرات (ميل = 1): **+2**")
    else:
        explain.append("المؤشرات مختلطة/محايدة (لا يوجد Bonus للاتفاق).")

    # Data quality penalty
    q = _df_quality_snapshot(df)
    candles = int(q.get("candles") or 0)
    if candles and candles < 220:
        # كلما قل التاريخ زادت العقوبة
        if candles < 120:
            score -= 20
            explain.append("تاريخ قصير جدًا (<120 شمعة): **-20**")
        else:
            score -= 10
            explain.append("تاريخ أقل من 220 شمعة: **-10**")

    if not q.get("ok") and q.get("issues"):
        # أعمدة ناقصة أو قيم غير منطقية
        score -= 15
        explain.append("ملاحظات جودة بيانات (أعمدة ناقصة/قيم غير منطقية): **-15**")

    # Clamp
    score_i = int(round(_clamp(score, 0, 100)))
    explain.append(f"النتيجة النهائية (بعد الحد) = **{score_i}/100**")
    explain.append(f"ملخص الاتجاه: {overall} | صافي الميل = **{tilt:+d}**")

    return score_i, explain


def _render_advanced_section(df: pd.DataFrame, symbol: str, interval: str):
    if not _ADV_AVAILABLE or compute_advanced_technical_pack is None:
        st.warning("حزمة المؤشرات المتقدمة غير متوفرة داخل هذا الإصدار.")
        st.caption("تأكد من وجود: technical_indicators/advanced.py")
        return

    if df is None or df.empty:
        st.warning("لا توجد بيانات سعرية كافية لحساب المؤشرات المتقدمة.")
        return

    st.markdown("## 🧠 المؤشرات المتقدمة")
    st.caption("هدف هذا القسم: تقديم إشارات/أدلة إضافية **كمساند** للقرار، وليس كبديل عن إدارة المخاطر.")

    # شارة جودة بيانات الشموع
    _render_quality_badge(df)

    with st.spinner("جاري حساب المؤشرات المتقدمة..."):
        pack = compute_advanced_technical_pack(df, symbol=symbol, timeframe=interval)

    if not isinstance(pack, dict) or not pack:
        st.error("تعذر إنتاج نتائج المؤشرات المتقدمة (pack فارغ/غير صالح).")
        return

    # حفظ النتائج في قاعدة البيانات (كاش) ليستفيد منها المستشار وتبقى "مسجّلة".
    try:
        from ai_engine_core.db import save_advanced_indicators

        save_advanced_indicators(symbol=symbol, interval=interval, payload=pack)
    except Exception:
        pass

    # ✅ Score موحد + تفسير
    score, explain = _advanced_unified_score(pack, df)
    avg_conf, tilt, overall = _pack_score(pack)

    c1, c2, c3, c4 = st.columns([1.1, 1.1, 1.1, 2.7])
    with c1:
        st.metric("Score موحد", f"{score}/100")
    with c2:
        st.metric("متوسط الثقة", f"{avg_conf}%")
    with c3:
        st.metric("صافي الميل", f"{tilt:+d}")
    with c4:
        st.info(f"**النتيجة التنفيذية:** {overall}")

    with st.expander("لماذا أخذت هذه الدرجة؟ (Explainability)", expanded=False):
        st.write("\n".join([f"- {x}" for x in explain]))

    with st.expander("كيف تقرأ هذا القسم؟ (قواعد بسيطة)", expanded=False):
        st.write(
            "- **Score الموحد**: يجمع (ثقة المؤشرات + اتفاقها + جودة بيانات الشموع).\n"
            "- **الاتجاه (إيجابي/سلبي/مختلط)**: يصف الميل العام، لكنه لا يساوي توصية شراء/بيع وحده.\n"
            "- إذا كانت جودة الشموع ضعيفة أو التاريخ قصير، تعامل مع النتائج على أنها **استرشادية فقط**.\n"
            "- لا تعتمد على مؤشر واحد: الأفضل رؤية **تقاطع الأدلة** مع إدارة مخاطر واضحة."
        )

    st.divider()

    # العناصر
    rls = pack.get("rls_forecast", {}) or {}
    wrsi = pack.get("chaos_wrsi", {}) or {}
    vp = pack.get("volume_profile_clusters", {}) or {}
    tl = pack.get("trendline_breakout", {}) or {}

    with st.expander("1) توقع RLS (اتجاه/ارتداد للمتوسط)", expanded=True):
        st.caption("**ماذا يعني؟** يتتبع الاتجاه ويقدّر احتمال الاستمرار أو الارتداد نحو المتوسط. "
                   "يُستخدم كـ *تأكيد* مع باقي الأدلة (وليس قرار منفرد).")
        _render_indicator_block("توقع RLS", rls)

    with st.expander("2) RSI مُوزّن ديناميكيًا (Chaos WRSI)", expanded=False):
        st.caption("**ماذا يعني؟** زخم أكثر حساسية للسياق: يفرق بين زخم صحي وزخم مُنهك. "
                   "يفضل قراءته مع الاتجاه العام والدعوم/المقاومات.")
        _render_indicator_block("RSI مُوزّن ديناميكيًا", wrsi)

    with st.expander("3) شرائح الحجم السعري (Volume Profile Clusters)", expanded=False):
        st.caption("**ماذا يعني؟** يحدد مناطق تكدّس أحجام قد تعمل كدعوم/مقاومات ديناميكية. "
                   "يساعدك تعرف أين تركز الشراء/البيع تاريخيًا.")
        _render_indicator_block("شرائح الحجم السعري", vp)

    with st.expander("4) مرشد اختراق الترند (Trendline Breakout)", expanded=False):
        st.caption("**ماذا يعني؟** يرصد كسر خط اتجاه/قناة مع شروط تأكيد لتقليل الإشارات الكاذبة. "
                   "استخدمه دائمًا مع وقف خسارة واضح.")
        _render_indicator_block("اختراق الترند", tl)

    st.caption("✅ ملاحظة: نتائج هذا القسم تُستخدم كذلك داخل **المستشار (AI)** ضمن الحزمة الفنية (Technical Pack).")


def view_technical(symbol: str, interval: str = "1d"):
    st.subheader("📈 التحليل الفني")

    # جلب بيانات الرسم/السعر
    df = None
    try:
        df = get_chart_history(symbol, period="1y", interval=interval)
    except Exception as e:
        st.error(f"تعذر جلب البيانات السعرية للرسم: {e}")

    # تبويبات داخل التحليل الفني (بدون حذف)
    tab1, tab2 = st.tabs(["ملخص فني", "مؤشرات متقدمة"])

    with tab1:
        st.markdown("### الرسم الفني (مرن)")

        # شارة حداثة البيانات (Data Freshness)
        try:
            if df is not None and (not df.empty):
                last_bar = df.index[-1]
                st.caption(
                    f"آخر شمعة: **{str(last_bar)}** | المصدر: **Yahoo/yfinance** | الفاصل: **{interval}**"
                )
        except Exception:
            pass

        # ✅ إصلاح: views.shared._render_technical_chart_flex لا يستقبل df أو key.
        try:
            _render_technical_chart_flex(symbol, period="1y", interval=interval)
        except Exception as e:
            st.warning(f"تعذر عرض الرسم المرن: {e}")
            if df is not None and not df.empty:
                st.dataframe(df.tail(10), width="stretch")

        st.caption("ملاحظة: هذا القسم هو الموجود سابقاً — لم يتم حذفه أو تغييره إلا بقدر تنظيم العرض داخل تبويب.")

    with tab2:
        _render_advanced_section(df, symbol=symbol, interval=interval)


def render_technical_tab(symbol: str, interval: str = "1d"):
    """Compatibility wrapper.

    The analysis router expects this name.
    We keep the actual implementation in `view_technical`.
    """
    return view_technical(symbol, interval=interval)
