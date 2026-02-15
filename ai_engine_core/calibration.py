# ai_engine_core/calibration.py
import json
from typing import Dict, Any, List, Optional, Tuple

import numpy as np
import pandas as pd

from .db import fetch_table
from .logging_learning import _set_weight, _get_weight


def _extract_score(report_json: Any) -> Optional[float]:
    try:
        if report_json is None:
            return None
        if isinstance(report_json, str):
            report = json.loads(report_json)
        elif isinstance(report_json, dict):
            report = report_json
        else:
            return None
        v = report.get("total_score")
        if v is None:
            # some versions store under engine
            v = report.get("score") or report.get("total")
        return float(v) if v is not None else None
    except Exception:
        return None


def _extract_return(outcome_json: Any) -> Optional[float]:
    """Return % (not fraction)."""
    try:
        if outcome_json is None:
            return None
        if isinstance(outcome_json, str):
            out = json.loads(outcome_json)
        elif isinstance(outcome_json, dict):
            out = outcome_json
        else:
            return None
        # prefer explicit pct
        for k in ("return_pct", "outcome_return_pct", "ret_pct", "pnl_pct"):
            if k in out and out[k] is not None:
                return float(out[k])
        # fallback: if return given as fraction
        if "return" in out and out["return"] is not None:
            r = float(out["return"])
            return r * 100.0 if abs(r) < 2 else r
        return None
    except Exception:
        return None


def load_log_dataset(timeframe: str, horizon_days: int = 20, max_rows: int = 5000) -> pd.DataFrame:
    """Build dataset from ai_signals + ai_outcomes tables (best-effort)."""
    tf = str(timeframe or "").strip().upper()
    sig = fetch_table("ai_signals", limit=max_rows) or []
    out = fetch_table("ai_outcomes", limit=max_rows) or []

    df_sig = pd.DataFrame(sig)
    df_out = pd.DataFrame(out)

    if df_sig.empty:
        return pd.DataFrame(columns=["score", "ret"])

    df = df_sig.copy()
    # filter timeframe if present
    if "timeframe" in df.columns:
        df = df[df["timeframe"].astype(str).str.upper() == tf]

    # join outcomes if possible
    if not df_out.empty and "signal_id" in df_out.columns and "id" in df.columns:
        df_out2 = df_out.copy()
        # filter horizon if available
        if "horizon_days" in df_out2.columns:
            df_out2 = df_out2[df_out2["horizon_days"].astype(str) == str(horizon_days)]
        df = df.merge(df_out2, left_on="id", right_on="signal_id", how="left", suffixes=("", "_out"))

    # score extraction
    df["score"] = df.get("score", None)
    if "report_json" in df.columns:
        df["score"] = df["report_json"].apply(_extract_score)

    # return extraction
    if "outcome_json" in df.columns:
        df["ret"] = df["outcome_json"].apply(_extract_return)
    elif "outcome_return_pct" in df.columns:
        df["ret"] = pd.to_numeric(df["outcome_return_pct"], errors="coerce")
    elif "return_pct" in df.columns:
        df["ret"] = pd.to_numeric(df["return_pct"], errors="coerce")
    else:
        df["ret"] = np.nan

    df = df[["score", "ret"]].dropna()
    df = df[(df["score"].abs() < 1e6) & (df["ret"].abs() < 1e6)]
    return df


def calibrate_thresholds(
    timeframe: str,
    horizon_days: int = 20,
    min_trades: int = 30,
    grid_step: float = 1.0,
    save: bool = True,
) -> Dict[str, Any]:
    """Calibrate score thresholds using logged outcomes.

    This is intentionally lightweight (fast & safe):
    - Optimizes thresholds to maximize average return with a minimum trade count.
    - Stores results in ai_weights under keys:
      th_buy|tf=<TF>, th_strong_buy|tf=<TF>, th_sell|tf=<TF>
    """
    tf = str(timeframe or "").strip().upper()
    data = load_log_dataset(tf, horizon_days=horizon_days)

    result = {
        "timeframe": tf,
        "horizon_days": horizon_days,
        "rows": int(len(data)),
        "used": False,
        "thresholds": {},
        "note": "",
    }

    if data.empty or len(data) < min_trades:
        result["note"] = "لا توجد بيانات كافية في السجلات للمعايرة."
        return result

    scores = data["score"].astype(float).values
    rets = data["ret"].astype(float).values

    # Search ranges around typical defaults
    buy_candidates = np.arange(2.0, 9.0 + 1e-9, grid_step)
    strong_candidates = np.arange(6.0, 13.0 + 1e-9, grid_step)
    sell_candidates = np.arange(-8.0, -1.0 + 1e-9, grid_step)

    best = None  # (objective, th_buy, th_strong, th_sell, stats)
    for th_buy in buy_candidates:
        sel_buy = scores >= th_buy
        n_buy = int(sel_buy.sum())
        if n_buy < min_trades:
            continue
        mean_buy = float(np.nanmean(rets[sel_buy]))
        win_buy = float(np.nanmean((rets[sel_buy] > 0).astype(float)))

        for th_strong in strong_candidates:
            if th_strong < th_buy:
                continue
            sel_strong = scores >= th_strong
            n_strong = int(sel_strong.sum())
            if n_strong < max(10, min_trades // 3):
                continue
            mean_strong = float(np.nanmean(rets[sel_strong]))
            win_strong = float(np.nanmean((rets[sel_strong] > 0).astype(float)))

            for th_sell in sell_candidates:
                sel_sell = scores <= th_sell
                n_sell = int(sel_sell.sum())
                # sell side is optional; keep it reasonable
                if n_sell < 10:
                    continue
                mean_sell = float(np.nanmean(rets[sel_sell]))

                # Objective: prioritize robust mean returns & enough samples
                obj = (mean_buy * np.sqrt(n_buy)) + (0.6 * mean_strong * np.sqrt(n_strong)) - (0.2 * abs(mean_sell) * np.sqrt(n_sell))

                stats = {
                    "n_buy": n_buy,
                    "mean_buy": mean_buy,
                    "win_buy": win_buy,
                    "n_strong": n_strong,
                    "mean_strong": mean_strong,
                    "win_strong": win_strong,
                    "n_sell": n_sell,
                    "mean_sell": mean_sell,
                }

                if best is None or obj > best[0]:
                    best = (obj, float(th_buy), float(th_strong), float(th_sell), stats)

    if best is None:
        result["note"] = "تعذر إيجاد thresholds مناسبة (قد تكون السجلات قليلة/غير متوازنة)."
        return result

    _, th_buy, th_strong, th_sell, stats = best
    result["thresholds"] = {"th_buy": th_buy, "th_strong_buy": th_strong, "th_sell": th_sell}
    result["stats"] = stats
    result["used"] = True

    if save:
        _set_weight(f"th_buy|tf={tf}", th_buy)
        _set_weight(f"th_strong_buy|tf={tf}", th_strong)
        _set_weight(f"th_sell|tf={tf}", th_sell)

    return result


def get_current_thresholds(timeframe: str) -> Dict[str, float]:
    tf = str(timeframe or "").strip().upper()
    return {
        "th_buy": float(_get_weight(f"th_buy|tf={tf}", 4)),
        "th_strong_buy": float(_get_weight(f"th_strong_buy|tf={tf}", 8)),
        "th_sell": float(_get_weight(f"th_sell|tf={tf}", -5)),
    }
