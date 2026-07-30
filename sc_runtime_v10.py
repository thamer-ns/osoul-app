"""SC-V92.5 parity runtime layered on Osoli V9."""
from __future__ import annotations

import copy
import re
import threading
import time
from typing import Any

from ai_engine_core.sc_feature_pack_v925 import SC_FEATURE_VERSION, build_sc_feature_pack
from sc_runtime_v9 import install_sc_runtime_v9
from sc_runtime_v9 import runtime_status as _runtime_status_v9

_INSTALL_LOCK = threading.RLock()
_INSTALLED = False


def _asset_context(symbol: str) -> tuple[str, str]:
    raw = str(symbol or "").strip().upper()
    compact = raw.replace("/", "").replace("-", "")
    if raw.endswith(".SR") or raw.isdigit() or raw in {"TASI", "^TASI", "^TASI.SR"}:
        return ("index", "SAUDI") if "TASI" in raw else ("stock", "SAUDI")
    if raw.endswith("=F"):
        return "future", "GLOBAL"
    if raw.startswith("^"):
        return "index", "GLOBAL"
    if re.fullmatch(r"(BTC|ETH|SOL|XRP|BNB|ADA|DOGE|AVAX|DOT|LINK)(USD|USDT)", compact):
        return "crypto", "CRYPTO"
    currencies = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "SAR", "CNY", "HKD"}
    if len(compact) == 6 and compact[:3] in currencies and compact[3:] in currencies:
        return "forex", "FOREX"
    return "stock", "US"


def _install_feature_contract() -> None:
    import sc_runtime_v8 as runtime_v8

    def append_feature_pack(report: dict[str, Any], context: Any) -> dict[str, Any]:
        started = time.perf_counter()
        asset_class, market = _asset_context(str(context.symbol))
        pack = build_sc_feature_pack(context.closed_history, context.interval, asset_class, market)
        report["sc_feature_pack"] = pack
        engine_meta = report.get("engine_meta")
        if not isinstance(engine_meta, dict):
            engine_meta = {}
        engine_meta["sc_feature_pack"] = {
            "version": SC_FEATURE_VERSION,
            "indicator_contract": "SC-V92.5/SC-FXM-V16",
            "closed_candles_only": True,
            "fingerprint": context.fingerprint,
            "qualified": bool(pack.get("qualified")),
            "priority": "cluster_then_pivot_then_secondary",
        }
        report["engine_meta"] = engine_meta
        features = report.get("features")
        if not isinstance(features, dict):
            features = {}
        if pack.get("ok"):
            sr = pack.get("sr") if isinstance(pack.get("sr"), dict) else {}
            support = sr.get("support") if isinstance(sr.get("support"), dict) else {}
            resistance = sr.get("resistance") if isinstance(sr.get("resistance"), dict) else {}
            risk_plan = pack.get("risk_plan") if isinstance(pack.get("risk_plan"), dict) else {}
            veto = pack.get("opposition_veto") if isinstance(pack.get("opposition_veto"), dict) else {}
            features.update(
                {
                    "sc_direction": int(pack.get("direction") or 0),
                    "sc_event_direction": int(pack.get("event_direction") or 0),
                    "sc_confidence": int(pack.get("confidence") or 0),
                    "sc_qualified": int(bool(pack.get("qualified"))),
                    "sc_support_cluster": support.get("level"),
                    "sc_support_touches": int(support.get("touches") or 0),
                    "sc_resistance_cluster": resistance.get("level"),
                    "sc_resistance_touches": int(resistance.get("touches") or 0),
                    "sc_opposition_veto": int(bool(veto.get("blocked"))),
                    "sc_target_count": int(risk_plan.get("target_count") or 0),
                    "sc_short_plan": int(bool(risk_plan.get("short_plan"))),
                }
            )
        report["features"] = features
        report["sc_alignment"] = {
            "available": bool(pack.get("ok")),
            "qualified": bool(pack.get("qualified")),
            "direction": int(pack.get("direction") or 0),
            "event": pack.get("event_code"),
            "confidence": int(pack.get("confidence") or 0),
            "opposition_veto": bool((pack.get("opposition_veto") or {}).get("blocked")),
            "priority": list(pack.get("priority_order") or []),
        }
        try:
            import performance_runtime_v7 as performance

            performance.record_phase(
                context.symbol,
                context.interval,
                "sc_feature_pack_v925_ms",
                (time.perf_counter() - started) * 1000.0,
            )
        except Exception:
            pass
        return report

    append_feature_pack._osoli_sc_v925 = True  # type: ignore[attr-defined]
    runtime_v8.SC_FEATURE_VERSION = SC_FEATURE_VERSION
    runtime_v8.build_sc_feature_pack = build_sc_feature_pack
    runtime_v8._append_feature_pack = append_feature_pack  # noqa: SLF001


def runtime_status() -> dict[str, Any]:
    status = copy.deepcopy(_runtime_status_v9())
    status.update(
        {
            "runtime_version": "10.0",
            "feature_version": SC_FEATURE_VERSION,
            "indicator_contract": "SC-V92.5/SC-FXM-V16",
            "sr_cluster_priority": 1,
            "confirmed_pivot_priority": 2,
            "secondary_tools_priority": 3,
            "cluster_opposition_veto": True,
            "close_confirmed_role_reversal": True,
            "independent_target_pivots": True,
        }
    )
    return status


def install_sc_runtime_v10() -> None:
    global _INSTALLED
    if _INSTALLED:
        return
    with _INSTALL_LOCK:
        if _INSTALLED:
            return
        install_sc_runtime_v9()
        _install_feature_contract()
        _INSTALLED = True


__all__ = ["install_sc_runtime_v10", "runtime_status"]
