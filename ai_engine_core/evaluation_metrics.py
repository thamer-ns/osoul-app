"""Pure evaluation helpers for analysis outcomes.

Metrics are intentionally descriptive. They never change model weights and they
avoid random train/test splits for time-ordered market observations.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from typing import Any

import pandas as pd


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def parse_json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if value is None or value == "":
        return {}
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def brier_score(probabilities: list[float], outcomes: list[int]) -> float | None:
    pairs = []
    for probability, outcome in zip(probabilities, outcomes):
        p = finite(probability)
        if p is None or int(outcome) not in {0, 1}:
            continue
        pairs.append((max(0.0, min(1.0, p)), int(outcome)))
    if not pairs:
        return None
    return sum((probability - outcome) ** 2 for probability, outcome in pairs) / len(pairs)


def calibration_table(probabilities: list[float], outcomes: list[int], *, bins: int = 5) -> pd.DataFrame:
    rows = []
    for probability, outcome in zip(probabilities, outcomes):
        p = finite(probability)
        if p is None or int(outcome) not in {0, 1}:
            continue
        rows.append({"probability": max(0.0, min(1.0, p)), "outcome": int(outcome)})
    if not rows:
        return pd.DataFrame(columns=["bucket", "samples", "mean_confidence", "observed_win_rate", "calibration_gap"])
    frame = pd.DataFrame(rows)
    width = 1.0 / max(1, int(bins))
    frame["bucket_index"] = (frame["probability"] / width).astype(int).clip(0, bins - 1)
    output = []
    for index, group in frame.groupby("bucket_index", sort=True):
        low = index * width
        high = min(1.0, (index + 1) * width)
        mean_confidence = float(group["probability"].mean())
        observed = float(group["outcome"].mean())
        output.append(
            {
                "bucket": f"{low * 100:.0f}–{high * 100:.0f}%",
                "samples": int(len(group)),
                "mean_confidence": round(mean_confidence * 100.0, 2),
                "observed_win_rate": round(observed * 100.0, 2),
                "calibration_gap": round((mean_confidence - observed) * 100.0, 2),
            }
        )
    return pd.DataFrame(output)


def integrity_report(signals: pd.DataFrame, outcomes: pd.DataFrame) -> dict[str, Any]:
    signal_frame = signals.copy() if isinstance(signals, pd.DataFrame) else pd.DataFrame()
    outcome_frame = outcomes.copy() if isinstance(outcomes, pd.DataFrame) else pd.DataFrame()
    issues: list[str] = []
    duplicate_signals = int(signal_frame["id"].duplicated().sum()) if "id" in signal_frame.columns else 0
    duplicate_outcomes = int(outcome_frame["id"].duplicated().sum()) if "id" in outcome_frame.columns else 0
    signal_ids = set(signal_frame.get("id", pd.Series(dtype=str)).dropna().astype(str))
    outcome_signal_ids = outcome_frame.get("signal_id", pd.Series(dtype=str)).dropna().astype(str)
    orphan_outcomes = int((~outcome_signal_ids.isin(signal_ids)).sum()) if len(outcome_signal_ids) else 0
    invalid_json = 0
    if "report_json" in signal_frame.columns:
        invalid_json = int(sum(1 for value in signal_frame["report_json"] if value not in (None, "") and not parse_json_object(value)))
    nonfinite_returns = 0
    if "return_pct" in outcome_frame.columns:
        nonfinite_returns = int(sum(1 for value in outcome_frame["return_pct"] if value is not None and finite(value) is None))
    future_dates = 0
    now = datetime.now(timezone.utc)
    for frame, column in ((signal_frame, "created_at"), (outcome_frame, "exit_at")):
        if column not in frame.columns:
            continue
        values = pd.to_datetime(frame[column], errors="coerce", utc=True)
        future_dates += int((values > now).sum())

    for count, label in (
        (duplicate_signals, "معرفات إشارات مكررة"),
        (duplicate_outcomes, "معرفات نتائج مكررة"),
        (orphan_outcomes, "نتائج بلا إشارة أصلية"),
        (invalid_json, "تقارير JSON غير قابلة للقراءة"),
        (nonfinite_returns, "عوائد غير رقمية أو غير منتهية"),
        (future_dates, "تواريخ مستقبلية غير منطقية"),
    ):
        if count:
            issues.append(f"{label}: {count}")
    return {
        "pass": not issues,
        "issues": issues,
        "duplicate_signals": duplicate_signals,
        "duplicate_outcomes": duplicate_outcomes,
        "orphan_outcomes": orphan_outcomes,
        "invalid_json": invalid_json,
        "nonfinite_returns": nonfinite_returns,
        "future_dates": future_dates,
    }


def build_evaluation_dataset(signals: pd.DataFrame, outcomes: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(signals, pd.DataFrame) or signals.empty or "id" not in signals.columns:
        return pd.DataFrame()
    if not isinstance(outcomes, pd.DataFrame) or outcomes.empty or "signal_id" not in outcomes.columns:
        return pd.DataFrame()
    left = signals.copy()
    right = outcomes.copy()
    left["id"] = left["id"].astype(str)
    right["signal_id"] = right["signal_id"].astype(str)
    merged = right.merge(left, left_on="signal_id", right_on="id", how="inner", suffixes=("_outcome", "_signal"))
    if merged.empty:
        return merged

    confidences = []
    lifecycle = []
    direction = []
    schools = []
    plan_ids = []
    for value in merged.get("report_json", pd.Series(index=merged.index, dtype=object)):
        report = parse_json_object(value)
        consensus = report.get("school_consensus") if isinstance(report.get("school_consensus"), dict) else {}
        plan = report.get("risk_plan") if isinstance(report.get("risk_plan"), dict) else {}
        confidence = finite(report.get("confidence"))
        confidences.append(max(0.0, min(1.0, confidence / 100.0)) if confidence is not None else None)
        lifecycle.append(str(report.get("lifecycle_status") or "UNKNOWN"))
        direction.append(str(report.get("direction") or "neutral"))
        schools.append(" + ".join(str(item) for item in consensus.get("school_names") or []))
        plan_ids.append(plan.get("plan_id"))
    merged["predicted_probability"] = confidences
    merged["lifecycle"] = lifecycle
    merged["direction"] = direction
    merged["schools"] = schools
    merged["plan_id"] = plan_ids
    merged["win_clean"] = pd.to_numeric(merged.get("win"), errors="coerce")
    merged["return_clean"] = pd.to_numeric(merged.get("return_pct"), errors="coerce")
    merged["created_clean"] = pd.to_datetime(merged.get("created_at"), errors="coerce", utc=True)
    return merged.sort_values("created_clean", na_position="last", ignore_index=True)


def summary_metrics(dataset: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(dataset, pd.DataFrame) or dataset.empty:
        return {"samples": 0, "win_rate": None, "average_return": None, "brier": None, "tp_rate": None, "sl_rate": None}
    wins = pd.to_numeric(dataset.get("win_clean"), errors="coerce").dropna()
    returns = pd.to_numeric(dataset.get("return_clean"), errors="coerce").dropna()
    probabilities = dataset.get("predicted_probability", pd.Series(dtype=float)).tolist()
    outcomes = pd.to_numeric(dataset.get("win_clean"), errors="coerce").fillna(-1).astype(int).tolist()
    hit_tp = pd.to_numeric(dataset.get("hit_tp"), errors="coerce").dropna() if "hit_tp" in dataset.columns else pd.Series(dtype=float)
    hit_sl = pd.to_numeric(dataset.get("hit_sl"), errors="coerce").dropna() if "hit_sl" in dataset.columns else pd.Series(dtype=float)
    return {
        "samples": int(len(dataset)),
        "win_rate": float(wins.mean() * 100.0) if not wins.empty else None,
        "average_return": float(returns.mean()) if not returns.empty else None,
        "median_return": float(returns.median()) if not returns.empty else None,
        "brier": brier_score(probabilities, outcomes),
        "tp_rate": float(hit_tp.mean() * 100.0) if not hit_tp.empty else None,
        "sl_rate": float(hit_sl.mean() * 100.0) if not hit_sl.empty else None,
    }


def chronological_holdout(dataset: pd.DataFrame, *, test_fraction: float = 0.25) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split by time; future rows are never used to evaluate earlier rows."""
    if not isinstance(dataset, pd.DataFrame) or dataset.empty:
        return pd.DataFrame(), pd.DataFrame()
    ordered = dataset.sort_values("created_clean", na_position="last").reset_index(drop=True)
    cut = max(1, min(len(ordered) - 1, int(round(len(ordered) * (1.0 - test_fraction))))) if len(ordered) > 1 else len(ordered)
    return ordered.iloc[:cut].copy(), ordered.iloc[cut:].copy()
