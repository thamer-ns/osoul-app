from __future__ import annotations

from typing import Any, Dict

import pandas as pd

#liquidity_gate.py
def _to_num(s):
    try:
        return pd.to_numeric(s, errors="coerce")
    except Exception:
        return pd.Series(dtype=float)


def evaluate_liquidity_gate(
    df: pd.DataFrame,
    *,
    window: int = 20,
    min_avg_traded_value: float = 1_000_000.0,
    min_avg_volume: float = 30_000.0,
) -> Dict[str, Any]:
    """بوابة سيولة بسيطة للسوق: تفحص متوسط قيمة/حجم التداول لتخفيف التوصيات غير القابلة للتنفيذ."""
    out: Dict[str, Any] = {
        "pass": True,
        "severity": "ok",
        "confidence_cap": None,
        "reasons": [],
        "features": {},
    }
    try:
        if df is None or not isinstance(df, pd.DataFrame) or df.empty:
            out.update({"pass": False, "severity": "no_data", "confidence_cap": 50.0})
            out["reasons"].append("⚠️ لا توجد بيانات كافية لتقييم السيولة")
            out["features"].update({"liquidity_pass": 0})
            return out

        close = _to_num(df.get("Close"))
        vol = _to_num(df.get("Volume")).fillna(0)
        traded_val = (close * vol).replace([pd.NA], float("nan"))

        avg_val20 = float(traded_val.tail(window).dropna().mean()) if len(traded_val.dropna()) else 0.0
        avg_vol20 = float(vol.tail(window).dropna().mean()) if len(vol.dropna()) else 0.0
        active_days = int((vol.tail(window) > 0).sum()) if len(vol) else 0

        out["features"].update(
            {
                "avg_traded_value20": avg_val20,
                "avg_volume20": avg_vol20,
                "active_days20": active_days,
            }
        )

        severe = (avg_val20 < min_avg_traded_value * 0.5) or (avg_vol20 < min_avg_volume * 0.5) or (active_days < max(8, window // 2))
        weak = (avg_val20 < min_avg_traded_value) or (avg_vol20 < min_avg_volume)

        if severe:
            out.update({"pass": False, "severity": "low", "confidence_cap": 50.0})
            out["reasons"].append(
                f"⚠️ سيولة ضعيفة (متوسط قيمة تداول ~ {avg_val20:,.0f}) — التنفيذ قد يكون صعبًا."
            )
        elif weak:
            out.update({"pass": False, "severity": "medium", "confidence_cap": 60.0})
            out["reasons"].append(
                f"⚠️ سيولة متوسطة/ضعيفة (متوسط قيمة تداول ~ {avg_val20:,.0f}) — خفف الثقة."
            )

        out["features"]["liquidity_pass"] = 1 if out["pass"] else 0
        return out
    except Exception as e:
        out.update({"pass": False, "severity": "error", "confidence_cap": 55.0})
        out["reasons"].append(f"⚠️ تعذر تقييم السيولة: {type(e).__name__}")
        out["features"].update({"liquidity_pass": 0})
        return out
