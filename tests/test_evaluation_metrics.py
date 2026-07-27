from __future__ import annotations

import json

import pandas as pd
import pytest

from ai_engine_core.evaluation_metrics import (
    brier_score,
    build_evaluation_dataset,
    calibration_table,
    chronological_holdout,
    integrity_report,
    summary_metrics,
)


def test_brier_score_and_calibration_are_probability_aware():
    score = brier_score([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0])
    assert score == pytest.approx(0.025)

    table = calibration_table([0.9, 0.8, 0.2, 0.1], [1, 1, 0, 0], bins=5)
    assert int(table["samples"].sum()) == 4
    assert set(table.columns) == {
        "bucket",
        "samples",
        "mean_confidence",
        "observed_win_rate",
        "calibration_gap",
    }


def test_dataset_extracts_v4_contract_without_random_time_reordering():
    signals = pd.DataFrame(
        [
            {
                "id": "s1",
                "created_at": "2026-01-01T00:00:00Z",
                "timeframe": "1d",
                "strategy_name": "trend",
                "report_json": json.dumps(
                    {
                        "confidence": 80,
                        "direction": "buy",
                        "lifecycle_status": "ACTIONABLE",
                        "school_consensus": {"school_names": ["داو", "الزخم"]},
                        "risk_plan": {"plan_id": "p1"},
                    },
                    ensure_ascii=False,
                ),
            },
            {
                "id": "s2",
                "created_at": "2026-02-01T00:00:00Z",
                "timeframe": "1d",
                "strategy_name": "trend",
                "report_json": json.dumps(
                    {
                        "confidence": 30,
                        "direction": "sell",
                        "lifecycle_status": "HEADS_UP",
                        "school_consensus": {"school_names": ["البنية"]},
                        "risk_plan": {"plan_id": "p2"},
                    },
                    ensure_ascii=False,
                ),
            },
        ]
    )
    outcomes = pd.DataFrame(
        [
            {"id": "o1", "signal_id": "s1", "win": 1, "return_pct": 5, "hit_tp": 1, "hit_sl": 0},
            {"id": "o2", "signal_id": "s2", "win": 0, "return_pct": -2, "hit_tp": 0, "hit_sl": 1},
        ]
    )

    dataset = build_evaluation_dataset(signals, outcomes)
    assert dataset["signal_id"].tolist() == ["s1", "s2"]
    assert dataset.iloc[0]["schools"] == "داو + الزخم"
    assert summary_metrics(dataset)["samples"] == 2

    past, future = chronological_holdout(dataset, test_fraction=0.5)
    assert past.iloc[0]["signal_id"] == "s1"
    assert future.iloc[0]["signal_id"] == "s2"


def test_integrity_report_detects_orphans_duplicates_and_invalid_json():
    signals = pd.DataFrame(
        [
            {"id": "s1", "created_at": "2026-01-01", "report_json": "{"},
            {"id": "s1", "created_at": "2026-01-02", "report_json": "not-json"},
        ]
    )
    outcomes = pd.DataFrame(
        [
            {"id": "o1", "signal_id": "missing", "return_pct": "NaN"},
            {"id": "o1", "signal_id": "s1", "return_pct": 1.0},
        ]
    )

    audit = integrity_report(signals, outcomes)
    assert audit["pass"] is False
    assert audit["duplicate_signals"] == 1
    assert audit["duplicate_outcomes"] == 1
    assert audit["orphan_outcomes"] == 1
    assert audit["invalid_json"] == 1
    assert audit["nonfinite_returns"] == 1
