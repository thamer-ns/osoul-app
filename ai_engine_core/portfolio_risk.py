# ai_engine_core/portfolio_risk.py
import pandas as pd


def _safe_float(x, default=0.0):
    try:
        return float(x) if x is not None else float(default)
    except Exception:
        return float(default)


def compute_cash_percent(fin: dict):
    """
    fin: output من analytics.calculate_portfolio_metrics
    """
    cash = _safe_float((fin or {}).get("cash"), 0.0)
    mv = _safe_float((fin or {}).get("market_val_open"), 0.0)
    total = cash + mv
    if total <= 0:
        return 100.0
    return (cash / total) * 100.0


def position_sizing(entry: float, stop: float, equity: float, risk_pct: float = 1.0):
    """
    position sizing بسيط:
    risk_amount = equity * (risk_pct/100)
    shares = risk_amount / abs(entry-stop)
    """
    entry = _safe_float(entry, 0.0)
    stop = _safe_float(stop, 0.0)
    equity = _safe_float(equity, 0.0)
    risk_pct = _safe_float(risk_pct, 1.0)

    if entry <= 0 or stop <= 0 or equity <= 0:
        return {"ok": False, "reason": "invalid inputs"}

    per_share_risk = abs(entry - stop)
    if per_share_risk <= 0:
        return {"ok": False, "reason": "per_share_risk=0"}

    risk_amount = equity * (risk_pct / 100.0)
    shares = risk_amount / per_share_risk

    return {
        "ok": True,
        "risk_amount": round(risk_amount, 2),
        "per_share_risk": round(per_share_risk, 4),
        "shares": int(max(shares, 0)),
        "position_value": round(int(max(shares, 0)) * entry, 2),
    }


def portfolio_gates(trades_df: pd.DataFrame, symbol: str, cash_pct: float):
    """
    بوابات محفظة:
    - تركّز عالي: أكبر وزن > 35% = تحذير / >50% = منع
    - سيولة منخفضة: <5% = تحذير شديد
    """
    gates = {"pass": True, "reasons": [], "warnings": []}

    if trades_df is None or trades_df.empty:
        return gates

    if "status" not in trades_df.columns or "market_value" not in trades_df.columns:
        return gates

    op = trades_df[trades_df["status"].astype(str).str.lower().str.contains("open")]
    if op.empty:
        return gates

    total_mv = _safe_float(op["market_value"].sum(), 0.0)
    if total_mv <= 0:
        return gates

    max_w = (_safe_float(op["market_value"].max(), 0.0) / total_mv) * 100.0

    if max_w > 50:
        gates["pass"] = False
        gates["reasons"].append("تركيز المحفظة عالي جداً (أكبر وزن > 50%) — يفضّل عدم زيادة المخاطرة.")
    elif max_w > 35:
        gates["warnings"].append("تركيز المحفظة مرتفع (أكبر وزن > 35%) — خفّف/نوّع.")

    if cash_pct < 5:
        gates["warnings"].append("السيولة أقل من 5% — المرونة ضعيفة في التصحيح.")
    elif cash_pct < 12:
        gates["warnings"].append("السيولة أقل من 12% — راقب إدارة المخاطر.")

    # وزن السهم الحالي
    try:
        sym = str(symbol)
        row = op[op["symbol"].astype(str) == sym]
        if not row.empty:
            w = (_safe_float(row.iloc[0].get("market_value"), 0.0) / total_mv) * 100.0
            gates["symbol_weight_pct"] = round(w, 2)
    except Exception:
        pass

    return gates
