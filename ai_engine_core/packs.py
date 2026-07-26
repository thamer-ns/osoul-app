"""Stable pack builders for the Osoli AI engine.

Advanced indicators v2 expose signed direction and independent confidence. The
technical score therefore uses directional evidence instead of incorrectly
boosting bullish and bearish signals alike merely because confidence is high.
"""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from .ohlcv import _ensure_ohlcv_columns
from .indicators import _compute_indicators
from .technicals import (
    _analyze_financial_golden_rules,
    _analyze_ichimoku,
    _analyze_market_structure,
    _detect_advanced_patterns,
    _detect_liquidity_sweep,
    _detect_order_block,
)
from .vsa import analyze_vsa

try:
    from technical_indicators import compute_advanced_technical_pack
except Exception:  # pragma: no cover
    compute_advanced_technical_pack = None


def _sf(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except Exception:
        return float(default)


def _safe_merge_features(*dicts) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    for item in dicts:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key is not None:
                result[str(key)] = value
    return result


def _advanced_features(pack: Dict[str, Any]) -> Dict[str, Any]:
    features: Dict[str, Any] = {}
    top = pack.get("features") or {}
    if isinstance(top, dict):
        for key, value in top.items():
            if isinstance(value, (int, float, bool)):
                features[f"adv_{key}"] = float(value)
    for name in ("rls_forecast", "chaos_wrsi", "volume_profile_clusters", "trendline_breakout"):
        result = pack.get(name) or {}
        if not isinstance(result, dict):
            continue
        for key, value in (result.get("features") or {}).items():
            if isinstance(value, (int, float, bool)):
                features[f"adv_{name}_{key}"] = float(value)
    return features


def build_technical_pack(
    df: pd.DataFrame,
    symbol: str = "",
    timeframe: str = "1d",
    indicators: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    df = _ensure_ohlcv_columns(df)
    ind = indicators or _compute_indicators(df)

    score = 0.0
    reasons: list[str] = []
    features: Dict[str, Any] = {}

    s_candle, o_candle = _detect_advanced_patterns(df)
    s_struct, o_struct = _analyze_market_structure(df)
    s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
    s_ob, o_ob, f_ob = _detect_order_block(df)
    s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)

    score += sum(_sf(x) for x in (s_candle, s_struct, s_liq, s_ob, s_ichi))
    reasons.extend((o_struct or []) + (o_candle or []) + (o_liq or []) + (o_ob or []) + (o_ichi or []))
    features = _safe_merge_features(features, f_liq or {}, f_ob or {}, f_ichi or {})

    try:
        features["close"] = float(df["Close"].iloc[-1])
        for name in ("rsi14", "macd", "adx14", "sma50", "sma200", "atr14"):
            series = ind.get(name)
            if isinstance(series, pd.Series) and not pd.isna(series.iloc[-1]):
                features[name] = float(series.iloc[-1])
    except Exception:
        import logging
        logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)

    advanced = None
    if compute_advanced_technical_pack is not None:
        try:
            advanced = compute_advanced_technical_pack(df, symbol=symbol, timeframe=timeframe)
            if isinstance(advanced, dict):
                direction = _sf(advanced.get("direction_score"), 0.0)
                confidence = max(0.0, min(100.0, _sf(advanced.get("confidence"), 0.0)))
                contribution = (direction / 100.0) * (confidence / 100.0) * 4.0
                score += contribution
                features.update(_advanced_features(advanced))
                features["adv_direction_score"] = direction
                features["adv_confidence"] = confidence
                features["adv_score_contribution"] = contribution
                if advanced.get("summary"):
                    reasons.append(f"المؤشرات المتقدمة: {advanced['summary']}")
                reasons.extend([str(x) for x in (advanced.get("evidence") or [])[:6]])
                try:
                    from .db import save_advanced_indicators

                    save_advanced_indicators(
                        symbol=str(symbol),
                        timeframe=str(timeframe),
                        indicators=advanced,
                    )
                except Exception:
                    import logging
                    logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
        except Exception as exc:
            reasons.append(f"تعذر حساب المؤشرات المتقدمة: {exc}")

    direction_hint = "buy" if score >= 2 else "sell" if score <= -2 else "neutral"
    return {
        "score": round(float(score), 2),
        "reasons": reasons[:30],
        "features": features,
        "direction_hint": direction_hint,
        "symbol": str(symbol),
        "timeframe": str(timeframe),
        "advanced": advanced,
    }


def build_vsa_pack(df: pd.DataFrame, indicators: Dict[str, Any] | None = None) -> Dict[str, Any]:
    df = _ensure_ohlcv_columns(df)
    score, reasons, features = analyze_vsa(df)
    return {
        "score": round(float(score), 2),
        "reasons": (reasons or [])[:20],
        "features": features or {},
    }


def build_fundamental_pack(symbol: str) -> Dict[str, Any]:
    try:
        score, reasons, meta = _analyze_financial_golden_rules(symbol)
    except Exception:
        score, reasons, meta = 0, [], {}
    features = meta.get("_fund_features", {}) if isinstance(meta, dict) else {}
    return {
        "score": round(float(score), 2),
        "reasons": (reasons or [])[:20],
        "features": features or {},
        "meta": meta if isinstance(meta, dict) else {},
    }
