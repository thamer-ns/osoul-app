from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional
import json
import math

import pandas as pd


def _extract_scores_from_df(df: pd.DataFrame) -> List[float]:
    vals: List[float] = []
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return vals
    if "report_json" in df.columns:
        for raw in df["report_json"].dropna().tolist():
            try:
                if isinstance(raw, dict):
                    r = raw
                else:
                    r = json.loads(raw)
                if isinstance(r, dict) and isinstance(r.get("total_score"), (int, float)):
                    vals.append(float(r["total_score"]))
            except Exception:
                continue
    if "score" in df.columns:
        for x in pd.to_numeric(df["score"], errors="coerce").dropna().tolist():
            vals.append(float(x))
    # unique-ish preserve order not necessary; keep all
    return vals


def _fetch_history(timeframe: Optional[str], sector: Optional[str], max_rows: int = 500) -> List[float]:
    try:
        from database import fetch_table
    except Exception:
        return []
    try:
        df = fetch_table("ai_signals")
    except Exception:
        return []
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    try:
        if timeframe and "timeframe" in df.columns:
            tf = str(timeframe).strip().lower()
            df = df[df["timeframe"].astype(str).str.lower() == tf]
        if sector and "sector" in df.columns:
            sec = str(sector).strip().lower()
            if sec:
                sub = df[df["sector"].astype(str).str.lower() == sec]
                # if sparse sector history, fallback later to timeframe only
                if len(sub) >= 20:
                    df = sub
        if len(df) > max_rows:
            # prefer recent if created_at exists
            if "created_at" in df.columns:
                try:
                    df = df.sort_values("created_at").tail(max_rows)
                except Exception:
                    df = df.tail(max_rows)
            else:
                df = df.tail(max_rows)
    except Exception:
        pass
    return _extract_scores_from_df(df)


def normalize_score(
    raw_score: float,
    *,
    timeframe: Optional[str] = None,
    sector: Optional[str] = None,
    rows: Optional[Iterable[float]] = None,
) -> Dict[str, Any]:
    out: Dict[str, Any] = {
        "available": False,
        "raw_score": float(raw_score),
        "n": 0,
        "mean": None,
        "std": None,
        "zscore": None,
        "percentile": None,
        "confidence_delta": 0.0,
        "strong_ok": True,
    }
    try:
        values = [float(x) for x in (rows if rows is not None else _fetch_history(timeframe, sector)) if x is not None and not (isinstance(x, float) and math.isnan(x))]
        out["n"] = len(values)
        if len(values) < 20:
            return out
        s = pd.Series(values, dtype=float)
        mu = float(s.mean())
        sd = float(s.std(ddof=0))
        # percentile rank (weak tie handling is OK here)
        pct = float((s <= float(raw_score)).mean() * 100.0)
        z = 0.0 if sd <= 1e-9 else float((float(raw_score) - mu) / sd)
        cdelta = max(-10.0, min(10.0, z * 4.0))
        strong_ok = (pct >= 60.0) or (z >= 0.25)
        out.update({
            "available": True,
            "mean": mu,
            "std": sd,
            "zscore": z,
            "percentile": pct,
            "confidence_delta": cdelta,
            "strong_ok": bool(strong_ok),
        })
        return out
    except Exception:
        return out
