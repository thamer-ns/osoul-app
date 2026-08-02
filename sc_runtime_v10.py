"""SC-V94.7 parity runtime layered on Osoli V9.

The filename remains stable for deployed imports. Runtime 10.1 installs the
current indicator sources, side-safe support/resistance bridge and closed-candle
feature contract.
"""
from __future__ import annotations
import copy
import re
import threading
import time
from typing import Any
import pandas as pd
from ai_engine_core.sc_feature_pack_v925 import (
    SC_FEATURE_VERSION, SC_INDICATOR_CONTRACT, SC_INDICATOR_SOURCES,
    build_sc_feature_pack, classify_current_role_levels,
)
from sc_runtime_v9 import install_sc_runtime_v9
from sc_runtime_v9 import runtime_status as _runtime_status_v9

_INSTALL_LOCK = threading.RLock()
_INSTALLED = False


def _asset_context(symbol: str) -> tuple[str, str]:
    raw = str(symbol or "").strip().upper()
    compact = raw.replace("/", "").replace("-", "")
    if raw.endswith(".SR") or raw.isdigit() or raw in {"TASI", "^TASI", "^TASI.SR"}:
        return ("index", "SAUDI") if "TASI" in raw else ("stock", "SAUDI")
    if raw.endswith("=F"): return "future", "GLOBAL"
    if raw.startswith("^"): return "index", "GLOBAL"
    if re.fullmatch(r"(BTC|ETH|SOL|XRP|BNB|ADA|DOGE|AVAX|DOT|LINK)(USD|USDT)", compact): return "crypto", "CRYPTO"
    currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "SAR", "CNY", "HKD"}
    if len(compact) == 6 and compact[:3] in currencies and compact[3:] in currencies: return "forex", "FOREX"
    return "stock", "US"


def _infer_interval(frame: pd.DataFrame) -> str:
    if not isinstance(frame, pd.DataFrame) or len(frame) < 3: return "1d"
    try:
        index = pd.to_datetime(frame.index, errors="coerce")
        valid = index[~pd.isna(index)]
        if len(valid) < 3: return "1d"
        seconds = float(pd.Series(valid).diff().dropna().dt.total_seconds().median())
    except Exception: return "1d"
    if seconds <= 90: return "1m"
    if seconds <= 180: return "2m"
    if seconds <= 450: return "5m"
    if seconds <= 1200: return "15m"
    if seconds <= 2700: return "30m"
    if seconds <= 5400: return "1h"
    if seconds <= 18000: return "4h"
    if seconds <= 129600: return "1d"
    if seconds <= 950400: return "1w"
    return "1mo"


def _install_compass_sources() -> None:
    from ai_engine_core import compass_contract as contract
    contract.CURRENT_STOCK_SOURCES = frozenset({"SC-V94.7-I", "SC-V94.7-D"})
    contract.LEGACY_STOCK_SOURCES = frozenset({"SC-V92-I", "SC-V92-D", "SC-V90-I", "SC-V90-D", "SC-V84-I", "SC-V84-D"})
    contract.CURRENT_OTHER_SOURCES = frozenset({"SC-FXM-V18.8"})
    contract.LEGACY_OTHER_SOURCES = frozenset({"SC-FXM-V16", "SC-FXM-V14", "SC-FXM-V8"})
    contract.INTRADAY_STOCK_SOURCES = frozenset({"SC-V94.7-I", "SC-V92-I", "SC-V90-I", "SC-V84-I"})
    contract.DAILY_STOCK_SOURCES = frozenset({"SC-V94.7-D", "SC-V92-D", "SC-V90-D", "SC-V84-D"})
    contract.OTHER_SOURCES = contract.CURRENT_OTHER_SOURCES | contract.LEGACY_OTHER_SOURCES
    contract.STRICT_SOURCES = contract.CURRENT_STOCK_SOURCES | contract.LEGACY_STOCK_SOURCES | contract.CURRENT_OTHER_SOURCES | contract.LEGACY_OTHER_SOURCES


def _side_safe_zones(frame: pd.DataFrame, *, lookback: int = 220, max_levels: int = 6) -> tuple[list[float], list[float]]:
    levels = classify_current_role_levels(frame, _infer_interval(frame), max_levels=max_levels, lookback=lookback)
    support = [float(item["level"]) for item in levels.get("support") or [] if isinstance(item, dict) and item.get("level") is not None]
    resistance = [float(item["level"]) for item in levels.get("resistance") or [] if isinstance(item, dict) and item.get("level") is not None]
    return support, resistance


def _install_side_safe_legacy_sr() -> None:
    from ai_engine_core import risk

    def support_resistance_zones(frame: pd.DataFrame, lookback: int = 120, max_levels: int = 6) -> tuple[list[float], list[float]]:
        return _side_safe_zones(frame, lookback=lookback, max_levels=max_levels)

    def analyze_sr(frame: pd.DataFrame):
        features = {"near_support": 0, "near_resistance": 0, "broke_support_confirm": 0, "sr_current_role_safe": 1}
        if not isinstance(frame, pd.DataFrame) or frame.empty or len(frame) < 30 or "Close" not in frame.columns: return 0, [], features
        close_series = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        if len(close_series) < 2 or float(close_series.iloc[-1]) <= 0: return 0, [], features
        close, score, observations = float(close_series.iloc[-1]), 0, []
        supports, resistances = _side_safe_zones(frame, lookback=220, max_levels=8)
        nearest_support = max((value for value in supports if value < close), default=None)
        nearest_resistance = min((value for value in resistances if value > close), default=None)
        try:
            high, low = pd.to_numeric(frame["High"], errors="coerce"), pd.to_numeric(frame["Low"], errors="coerce")
            previous = close_series.shift(1)
            true_range = pd.concat((high-low, (high-previous).abs(), (low-previous).abs()), axis=1).max(axis=1)
            atr_value = float(true_range.ewm(alpha=1/14, adjust=False).mean().iloc[-1])
        except Exception: atr_value = close*.01
        near_distance = max(close*.01, atr_value*.35)
        if nearest_support is not None and close-nearest_support <= near_distance:
            score += 1; features["near_support"] = 1; observations.append("🧩 قرب دعم حالي أسفل السعر")
        if nearest_resistance is not None and nearest_resistance-close <= near_distance:
            score -= 1; features["near_resistance"] = 1; observations.append("🧩 قرب مقاومة حالية أعلى السعر")
        if len(frame) >= 3:
            prior_supports, _ = _side_safe_zones(frame.iloc[:-1], lookback=220, max_levels=8)
            prior_close = float(close_series.iloc[-2])
            prior_support = max((value for value in prior_supports if value < prior_close), default=None)
            if prior_support is not None and float(close_series.iloc[-2]) < prior_support and float(close_series.iloc[-1]) < prior_support:
                score -= 2; features["broke_support_confirm"] = 1; observations.append("🧨 كسر دعم مؤكد بإغلاقين؛ تحول إلى مقاومة")
        return score, observations, features

    support_resistance_zones._osoli_sc_v947 = True
    analyze_sr._osoli_sc_v947 = True
    risk._support_resistance_zones = support_resistance_zones
    risk._analyze_sr = analyze_sr


def _install_feature_contract() -> None:
    import sc_runtime_v8 as runtime_v8

    def append_feature_pack(report: dict[str, Any], context: Any) -> dict[str, Any]:
        started = time.perf_counter()
        asset_class, market = _asset_context(str(context.symbol))
        pack = build_sc_feature_pack(context.closed_history, context.interval, asset_class, market)
        report["sc_feature_pack"] = pack
        engine_meta = report.get("engine_meta") if isinstance(report.get("engine_meta"), dict) else {}
        engine_meta["sc_feature_pack"] = {"version": SC_FEATURE_VERSION, "indicator_contract": SC_INDICATOR_CONTRACT, "closed_candles_only": True, "fingerprint": context.fingerprint, "qualified": bool(pack.get("qualified")), "priority": "current_role_cluster_then_pivot_then_secondary", "integrity_ok": bool((pack.get("integrity") or {}).get("ok"))}
        report["engine_meta"] = engine_meta
        features = report.get("features") if isinstance(report.get("features"), dict) else {}
        if pack.get("ok"):
            sr = pack.get("sr") if isinstance(pack.get("sr"), dict) else {}
            support = sr.get("support") if isinstance(sr.get("support"), dict) else {}
            resistance = sr.get("resistance") if isinstance(sr.get("resistance"), dict) else {}
            risk_plan = pack.get("risk_plan") if isinstance(pack.get("risk_plan"), dict) else {}
            veto = pack.get("opposition_veto") if isinstance(pack.get("opposition_veto"), dict) else {}
            integrity = pack.get("integrity") if isinstance(pack.get("integrity"), dict) else {}
            features.update({"sc_direction": int(pack.get("direction") or 0), "sc_event_direction": int(pack.get("event_direction") or 0), "sc_confidence": int(pack.get("confidence") or 0), "sc_qualified": int(bool(pack.get("qualified"))), "sc_support_cluster": support.get("level"), "sc_support_touches": int(support.get("touches") or 0), "sc_support_role_reversed": int(bool(support.get("role_reversed"))), "sc_resistance_cluster": resistance.get("level"), "sc_resistance_touches": int(resistance.get("touches") or 0), "sc_resistance_role_reversed": int(bool(resistance.get("role_reversed"))), "sc_opposition_veto": int(bool(veto.get("blocked"))), "sc_target_count": int(risk_plan.get("target_count") or 0), "sc_short_plan": int(bool(risk_plan.get("short_plan"))), "sc_integrity_ok": int(bool(integrity.get("ok"))), "sr_current_role_safe": 1})
        report["features"] = features
        report["sc_alignment"] = {"available": bool(pack.get("ok")), "qualified": bool(pack.get("qualified")), "direction": int(pack.get("direction") or 0), "event": pack.get("event_code"), "confidence": int(pack.get("confidence") or 0), "opposition_veto": bool((pack.get("opposition_veto") or {}).get("blocked")), "integrity_ok": bool((pack.get("integrity") or {}).get("ok")), "priority": list(pack.get("priority_order") or [])}
        try:
            import performance_runtime_v7 as performance
            performance.record_phase(context.symbol, context.interval, "sc_feature_pack_v947_ms", (time.perf_counter()-started)*1000.0)
        except Exception: pass
        return report

    append_feature_pack._osoli_sc_v947 = True
    runtime_v8.SC_FEATURE_VERSION = SC_FEATURE_VERSION
    runtime_v8.SC_INDICATOR_CONTRACT = SC_INDICATOR_CONTRACT
    runtime_v8.build_sc_feature_pack = build_sc_feature_pack
    runtime_v8._append_feature_pack = append_feature_pack


def runtime_status() -> dict[str, Any]:
    status = copy.deepcopy(_runtime_status_v9())
    status.update({"runtime_version": "10.1", "feature_version": SC_FEATURE_VERSION, "indicator_contract": SC_INDICATOR_CONTRACT, "sr_cluster_priority": 1, "confirmed_pivot_priority": 2, "secondary_tools_priority": 3, "current_role_sr_classification": True, "role_reversal_supported": True, "cluster_opposition_veto": True, "close_confirmed_role_reversal": True, "independent_target_pivots": True, "directional_geometry_invariant": True, "current_indicator_sources": list(SC_INDICATOR_SOURCES)})
    return status


def install_sc_runtime_v10() -> None:
    global _INSTALLED
    if _INSTALLED: return
    with _INSTALL_LOCK:
        if _INSTALLED: return
        install_sc_runtime_v9()
        _install_compass_sources()
        _install_side_safe_legacy_sr()
        _install_feature_contract()
        _INSTALLED = True


__all__ = ["install_sc_runtime_v10", "runtime_status"]
