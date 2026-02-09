from osoli_logging import log_exception

"""ai_engine_core/scenarios.py

This module provides a **stable import surface** for scenario building.

Why this exists:
- Some versions of the engine referenced `build_scenarios` from a dedicated module.
- In older/working versions, scenario logic lived inline in `reporting.py`.
- When refactoring, it's easy to forget adding the file, causing:
  `ModuleNotFoundError: ai_engine_core.scenarios`

Design:
- Keep it lightweight and dependency-safe.
- Accept packs + market dataframe (if available).
- Return a list of scenario dicts that UI/LLM prompt can display.
"""

from typing import Any, Dict, List, Optional


def _to_float(x: Any, default: float = 0.0) -> float:
    try:
        if x is None:
            return float(default)
        return float(x)
    except Exception:
        return float(default)


def build_scenarios(
    symbol: str,
    timeframe: str,
    price_df=None,
    technical: Optional[Dict[str, Any]] = None,
    vsa: Optional[Dict[str, Any]] = None,
    fundamental: Optional[Dict[str, Any]] = None,
    structure: Optional[Dict[str, Any]] = None,
    risk: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Build scenario list.

    The engine uses scenarios as *human-readable* action plans:
    - base / bullish / bearish
    - entries, invalidations, targets (best-effort)

    Notes:
    - If we don't have enough data, we return a minimal scenario.
    - This is intentionally conservative to avoid making strong claims
      when data is missing.
    """

    scenarios: List[Dict[str, Any]] = []
    try:
        symbol = str(symbol or "").strip().upper()
        timeframe = str(timeframe or "").strip()

        # -----------------------------
        # Current price (best effort)
        # -----------------------------
        last_price = 0.0
        try:
            if price_df is not None and getattr(price_df, "empty", True) is False:
                if "Close" in price_df.columns:
                    last_price = _to_float(price_df["Close"].iloc[-1], 0.0)
        except Exception:
            last_price = 0.0

        # Support/Resistance candidates from structure pack if present
        sup = 0.0
        res = 0.0
        if isinstance(structure, dict):
            sup = _to_float(structure.get("support", 0.0), 0.0)
            res = _to_float(structure.get("resistance", 0.0), 0.0)

        # Simple fallback: infer from recent candles
        if (sup <= 0 or res <= 0) and last_price > 0 and price_df is not None and getattr(price_df, "empty", True) is False:
            try:
                lo = _to_float(price_df["Low"].tail(40).min(), 0.0) if "Low" in price_df.columns else 0.0
                hi = _to_float(price_df["High"].tail(40).max(), 0.0) if "High" in price_df.columns else 0.0
                if sup <= 0:
                    sup = lo
                if res <= 0:
                    res = hi
            except Exception:
                pass

        # Risk gates suggestion
        stop = 0.0
        if sup > 0:
            stop = sup
        elif last_price > 0:
            stop = last_price * 0.97

        # Targets
        t1 = 0.0
        t2 = 0.0
        if res > 0 and last_price > 0:
            t1 = res
            t2 = max(res * 1.03, last_price * 1.05)
        elif last_price > 0:
            t1 = last_price * 1.03
            t2 = last_price * 1.06

        # Direction hint from technical pack
        direction = "neutral"
        if isinstance(technical, dict):
            direction = str(technical.get("direction", direction) or direction)

        base = {
            "name": "السيناريو الأساسي",
            "timeframe": timeframe,
            "direction": direction,
            "entry": last_price,
            "stop": stop,
            "targets": [t1, t2],
            "notes": [
                "هذه سيناريوهات إرشادية مبنية على أفضل البيانات المتاحة داخل التطبيق.",
                "عدّل نقاط الدخول/الوقف حسب سيولتك وخطتك وإدارة المخاطر.",
            ],
        }
        scenarios.append(base)

        # Bullish / Bearish wrappers
        if last_price > 0:
            scenarios.append(
                {
                    "name": "سيناريو صاعد (اختراق)",
                    "timeframe": timeframe,
                    "direction": "buy",
                    "trigger": res if res > 0 else last_price * 1.01,
                    "entry": (res if res > 0 else last_price * 1.01),
                    "stop": max(stop, last_price * 0.97) if stop > 0 else last_price * 0.97,
                    "targets": [t1, t2],
                    "notes": ["يفضّل تأكيد الاختراق بحجم تداول/إغلاق."]
                }
            )
            scenarios.append(
                {
                    "name": "سيناريو هابط (كسر دعم)",
                    "timeframe": timeframe,
                    "direction": "sell",
                    "trigger": sup if sup > 0 else last_price * 0.99,
                    "entry": (sup if sup > 0 else last_price * 0.99),
                    "stop": (last_price * 1.02),
                    "targets": [
                        sup * 0.97 if sup > 0 else last_price * 0.97,
                        sup * 0.94 if sup > 0 else last_price * 0.94,
                    ],
                    "notes": ["هذا السيناريو تحذيري — لا يُعتبر توصية بيع إلزامية."]
                }
            )

    except Exception as e:
        log_exception(e, "Scenario builder failed", level="DEBUG")
        return [
            {
                "name": "سيناريو (افتراضي)",
                "timeframe": str(timeframe or ""),
                "direction": "neutral",
                "entry": 0.0,
                "stop": 0.0,
                "targets": [],
                "notes": ["تعذر بناء السيناريو بسبب نقص بيانات/خطأ داخلي."],
            }
        ]

    return scenarios
