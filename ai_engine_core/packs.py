"""
ai_engine_core/packs.py

هذه الوحدة (packs) **اختيارية**.

سبب إضافتها:
بعض النسخ السابقة من ai_engine_core/reporting.py كانت تتوقع وجود pack builders:
  - build_technical_pack
  - build_vsa_pack
  - build_fundamental_pack

إذا كانت غير موجودة يظهر الخطأ:
RuntimeError: Missing pack builders. Expected ai_engine_core/packs.py ...

في مشروعك الحالي يوجد محركات التحليل داخل:
- technicals.py
- vsa.py
- indicators.py
- risk.py

فهنا نوفّر wrappers “builders” بشكل آمن (safe) لتوافق أي نسخة قديمة من reporting.py.
"""

from typing import Dict, Any, Tuple
import pandas as pd

from .ohlcv import _ensure_ohlcv_columns
from .indicators import _compute_indicators

from .technicals import (
    _detect_advanced_patterns,
    _analyze_market_structure,
    _detect_liquidity_sweep,
    _detect_order_block,
    _analyze_ichimoku,
    _analyze_financial_golden_rules,
)

from .vsa import analyze_vsa

# مؤشرات إضافية (Advanced) - اختيارية وآمنة (لا تكسر سلوك البرنامج)
try:
    from technical_indicators import compute_advanced_technical_pack
except Exception:  # pragma: no cover
    compute_advanced_technical_pack = None


def _safe_merge_features(*dicts) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for d in dicts:
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            if k is None:
                continue
            out[str(k)] = v
    return out


def build_technical_pack(
    df: pd.DataFrame,
    symbol: str = "",
    timeframe: str = "1d",
    indicators: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    يبني tech_pack بشكل بسيط وعملي:
    - يحسب مؤشرات
    - يشغّل الوحدات الأساسية الموجودة عندك (structure/candles/sr/liquidity/ob/ichimoku)
    ويرجع:
      {score, reasons, features, direction_hint}
    """
    df = _ensure_ohlcv_columns(df)
    ind = indicators or _compute_indicators(df)

    score = 0.0
    reasons = []
    features = {}

    # Core tech modules
    s_candle, o_candle = _detect_advanced_patterns(df)
    s_struct, o_struct = _analyze_market_structure(df)
    s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
    s_ob, o_ob, f_ob = _detect_order_block(df)
    s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)

    score += float(s_candle or 0) + float(s_struct or 0) + float(s_liq or 0) + float(s_ob or 0) + float(s_ichi or 0)
    reasons += (o_struct or []) + (o_candle or []) + (o_liq or []) + (o_ob or []) + (o_ichi or [])
    features = _safe_merge_features(features, f_liq or {}, f_ob or {}, f_ichi or {})

    # Add a few numeric features (safe)
    try:
        features["close"] = float(df["Close"].iloc[-1])
        if isinstance(ind.get("rsi14"), pd.Series) and not pd.isna(ind["rsi14"].iloc[-1]):
            features["rsi14"] = float(ind["rsi14"].iloc[-1])
        if isinstance(ind.get("macd"), pd.Series) and not pd.isna(ind["macd"].iloc[-1]):
            features["macd"] = float(ind["macd"].iloc[-1])
        if isinstance(ind.get("adx14"), pd.Series) and not pd.isna(ind["adx14"].iloc[-1]):
            features["adx14"] = float(ind["adx14"].iloc[-1])
        if isinstance(ind.get("sma50"), pd.Series) and not pd.isna(ind["sma50"].iloc[-1]):
            features["sma50"] = float(ind["sma50"].iloc[-1])
        if isinstance(ind.get("sma200"), pd.Series) and not pd.isna(ind["sma200"].iloc[-1]):
            features["sma200"] = float(ind["sma200"].iloc[-1])
        if isinstance(ind.get("atr14"), pd.Series) and not pd.isna(ind["atr14"].iloc[-1]):
            features["atr14"] = float(ind["atr14"].iloc[-1])
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/packs.py:106')


    # -------------------------------
    # Advanced Technical Indicators (اختياري)
    # -------------------------------
    if compute_advanced_technical_pack is not None:
        try:
            # schema موحّد: {name, features, signals, evidence, confidence, errors, meta}
            adv = compute_advanced_technical_pack(df, symbol=symbol, timeframe=timeframe)
            if isinstance(adv, dict):
                adv_features = adv.get("features") or {}
                if isinstance(adv_features, dict):
                    for k, v in adv_features.items():
                        if v is None:
                            continue
                        # نُسجّلها تحت بادئة adv_ لتفادي التعارض
                        try:
                            if isinstance(v, (int, float, bool)):
                                features[f"adv_{k}"] = float(v)
                        except Exception:
                            import logging
                            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/packs.py:127')

                # Evidence عربية
                adv_evidence = adv.get("evidence") or []
                if isinstance(adv_evidence, list):
                    reasons.extend([str(x) for x in adv_evidence if str(x).strip()])

                # Signals (نضيف ملخصاً بسيطاً كسطر في الأسباب)
                adv_signals = adv.get("signals") or []
                if isinstance(adv_signals, list) and adv_signals:
                    try:
                        sig_text = ", ".join([str(s.get("name", "")) for s in adv_signals if isinstance(s, dict) and s.get("name")])
                        if sig_text.strip():
                            reasons.append(f"إشارات متقدمة: {sig_text}")
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/packs.py:142')

                # Confidence boost محدود
                adv_conf = adv.get("confidence")
                if isinstance(adv_conf, (int, float)):
                    features["adv_confidence"] = float(adv_conf)
                    score += max(-2.0, min(2.0, (float(adv_conf) - 50.0) / 25.0))

                # Cache في DB (اختياري)
                try:
                    from .db import save_advanced_indicators

                    save_advanced_indicators(symbol=str(symbol), interval=str(timeframe), pack=adv)
                except Exception:
                    import logging
                    logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/packs.py:156')
        except Exception:  # pragma: no cover
            reasons.append("⚠️ تعذر حساب بعض المؤشرات المتقدمة (تم تجاهلها بأمان).")

    # Direction hint
    direction_hint = "neutral"
    try:
        if score >= 2:
            direction_hint = "buy"
        elif score <= -2:
            direction_hint = "sell"
    except Exception:
        direction_hint = "neutral"

    return {
        "score": round(float(score), 2),
        "reasons": reasons[:20],
        "features": features,
        "direction_hint": direction_hint,
        "symbol": str(symbol),
        "timeframe": str(timeframe),
    }


def build_vsa_pack(
    df: pd.DataFrame,
    indicators: Dict[str, Any] = None,
) -> Dict[str, Any]:
    """
    يبني vsa_pack باستخدام analyze_vsa الموجود عندك.
    """
    df = _ensure_ohlcv_columns(df)
    score, reasons, features = analyze_vsa(df)
    return {
        "score": round(float(score), 2),
        "reasons": (reasons or [])[:20],
        "features": features or {},
    }


def build_fundamental_pack(symbol: str) -> Dict[str, Any]:
    """
    يبني fund_pack من _analyze_financial_golden_rules الموجودة في technicals.py
    """
    try:
        s_fund, o_fund, meta = _analyze_financial_golden_rules(symbol)
    except Exception:
        s_fund, o_fund, meta = 0, [], {}

    feats = {}
    try:
        if isinstance(meta, dict):
            feats = meta.get("_fund_features", {}) or {}
    except Exception:
        feats = {}

    return {
        "score": round(float(s_fund), 2),
        "reasons": (o_fund or [])[:20],
        "features": feats,
        "meta": meta if isinstance(meta, dict) else {},
    }
