# ai_engine_core/portfolio_risk.py
import math
from typing import Optional

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
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/portfolio_risk.py:99')

    return gates


# ----------------------------------------------------------------------
# Performance & risk metrics (used by backtester / portfolio analytics)
# ----------------------------------------------------------------------

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return float(default)


def max_drawdown(equity: pd.Series) -> float:
    """Max drawdown as a positive fraction (e.g. 0.25 = -25%)."""
    if equity is None or len(equity) < 2:
        return 0.0
    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if eq.empty:
        return 0.0
    peak = eq.cummax()
    dd = (eq / peak) - 1.0
    return float((-dd.min()) if not dd.empty else 0.0)


def var_es_historical(returns: pd.Series, alpha: float = 0.05) -> tuple[float, float]:
    """Historical VaR/ES. Returns (VaR, ES) as positive loss fractions."""
    if returns is None or len(returns) < 10:
        return 0.0, 0.0
    r = pd.to_numeric(returns, errors="coerce").dropna()
    if r.empty:
        return 0.0, 0.0
    q = r.quantile(alpha)
    var = -float(q)
    tail = r[r <= q]
    es = -float(tail.mean()) if len(tail) else 0.0
    # Clamp negatives (in case of all-positive returns)
    return max(var, 0.0), max(es, 0.0)


def compute_perf_metrics(
    equity: pd.Series,
    dates: Optional[pd.Series] = None,
    risk_free_rate: float = 0.0,
    periods_per_year: int = 252,
) -> dict:
    """Compute a compact set of portfolio metrics.

    Parameters
    ----------
    equity: Series of portfolio values
    dates: optional Series of datetime-like; used for CAGR
    risk_free_rate: annual RF rate (e.g. 0.02)
    periods_per_year: 252 for daily bars
    """
    if equity is None or len(equity) < 2:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "var_95": 0.0,
            "es_95": 0.0,
        }

    eq = pd.to_numeric(equity, errors="coerce").dropna()
    if eq.empty or len(eq) < 2:
        return {
            "total_return": 0.0,
            "cagr": 0.0,
            "volatility": 0.0,
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "var_95": 0.0,
            "es_95": 0.0,
        }

    rets = eq.pct_change().dropna()
    total_return = float(eq.iloc[-1] / eq.iloc[0] - 1.0)

    # CAGR
    cagr = 0.0
    if dates is not None and len(dates) == len(equity):
        try:
            d = pd.to_datetime(dates, errors="coerce")
            d = d.loc[eq.index] if hasattr(eq, "index") else d
            d = d.dropna()
            if len(d) >= 2:
                years = (d.iloc[-1] - d.iloc[0]).days / 365.25
                if years > 0:
                    cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1.0)
        except Exception:
            cagr = 0.0
    else:
        # fallback based on periods
        years = len(eq) / float(periods_per_year)
        if years > 0:
            cagr = float((eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1.0)

    # Volatility
    vol = float(rets.std(ddof=0) * math.sqrt(periods_per_year)) if len(rets) else 0.0

    # Sharpe / Sortino
    rf_per_period = risk_free_rate / periods_per_year
    excess = rets - rf_per_period
    sharpe = float(excess.mean() / (rets.std(ddof=0) + 1e-12) * math.sqrt(periods_per_year)) if len(rets) else 0.0

    downside = rets[rets < 0]
    downside_std = float(downside.std(ddof=0)) if len(downside) else 0.0
    sortino = float(excess.mean() / (downside_std + 1e-12) * math.sqrt(periods_per_year)) if len(rets) else 0.0

    mdd = max_drawdown(eq)
    var95, es95 = var_es_historical(rets, alpha=0.05)

    return {
        "total_return": total_return,
        "cagr": cagr,
        "volatility": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": mdd,
        "var_95": var95,
        "es_95": es95,
    }
