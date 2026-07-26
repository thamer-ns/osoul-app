"""Stable pack builders for the Osoli AI engine."""
from __future__ import annotations

from typing import Any, Dict

import pandas as pd

from .indicators import _compute_indicators
from .ohlcv import _ensure_ohlcv_columns
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


def _merge_features(*items: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        for key, value in item.items():
            if key is not None:
                merged[str(key)] = value
    return merged


def build_technical_pack(
    df: pd.DataFrame,
    symbol: str = "",
    timeframe: str = "1d",
    indicators: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    frame = _ensure_ohlcv_columns(df)
    computed = indicators or _compute_indicators(frame)

    candle_score, candle_reasons = _detect_advanced_patterns(frame)
    structure_score, structure_reasons = _analyze_market_structure(frame)
    liquidity_score, liquidity_reasons, liquidity_features = _detect_liquidity_sweep(frame)
    block_score, block_reasons, block_features = _detect_order_block(frame)
    ichimoku_score, ichimoku_reasons, ichimoku_features = _analyze_ichimoku(frame)

    score = sum(
        float(value or 0)
        for value in (
            candle_score,
            structure_score,
            liquidity_score,
            block_score,
            ichimoku_score,
        )
    )
    reasons = (
        (structure_reasons or [])
        + (candle_reasons or [])
        + (liquidity_reasons or [])
        + (block_reasons or [])
        + (ichimoku_reasons or [])
    )
    features = _merge_features(
        liquidity_features or {},
        block_features or {},
        ichimoku_features or {},
    )

    try:
        features["close"] = float(frame["Close"].iloc[-1])
        for key in ("rsi14", "macd", "adx14", "sma50", "sma200", "atr14"):
            series = computed.get(key)
            if isinstance(series, pd.Series) and not series.empty and pd.notna(series.iloc[-1]):
                features[key] = float(series.iloc[-1])
    except Exception:
        pass

    advanced = None
    if callable(compute_advanced_technical_pack):
        try:
            advanced = compute_advanced_technical_pack(
                frame,
                symbol=symbol,
                timeframe=timeframe,
            )
        except Exception:
            advanced = None

    if isinstance(advanced, dict):
        advanced_direction = float(advanced.get("direction_score") or 0.0)
        advanced_confidence = float(advanced.get("confidence") or 0.0)
        # The core score has a small range. Advanced indicators may confirm it,
        # but cannot overpower the original engine.
        score += max(-3.0, min(3.0, advanced_direction / 30.0))
        features["advanced_direction_score"] = advanced_direction
        features["advanced_confidence"] = advanced_confidence
        features["advanced_bias"] = advanced.get("bias", "neutral")
        for key, value in (advanced.get("features") or {}).items():
            if isinstance(value, (int, float, bool, str)) or value is None:
                features[f"advanced.{key}"] = value
        reasons.extend(str(x) for x in (advanced.get("evidence") or [])[:12])
        for signal in (advanced.get("signals") or [])[:8]:
            if isinstance(signal, dict):
                reasons.append(
                    f"إشارة متقدمة {signal.get('type', 'INFO')}: "
                    f"{signal.get('reason', signal.get('kind', ''))}"
                )
        try:
            from .db import save_advanced_indicators

            save_advanced_indicators(
                symbol=str(symbol),
                timeframe=str(timeframe),
                indicators=advanced,
            )
        except Exception:
            pass

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


def build_vsa_pack(
    df: pd.DataFrame,
    indicators: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    del indicators
    frame = _ensure_ohlcv_columns(df)
    score, reasons, features = analyze_vsa(frame)
    return {
        "score": round(float(score or 0.0), 2),
        "reasons": (reasons or [])[:30],
        "features": features or {},
    }


def build_fundamental_pack(symbol: str) -> Dict[str, Any]:
    try:
        score, reasons, meta = _analyze_financial_golden_rules(symbol)
    except Exception:
        score, reasons, meta = 0.0, [], {}
    features = {}
    if isinstance(meta, dict):
        features = meta.get("_fund_features", {}) or {}
    return {
        "score": round(float(score or 0.0), 2),
        "reasons": (reasons or [])[:30],
        "features": features,
        "meta": meta if isinstance(meta, dict) else {},
    }
