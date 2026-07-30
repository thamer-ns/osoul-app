from __future__ import annotations

import math

import pandas as pd

from ai_engine_core import sc_feature_pack_v925 as sc


def _frame(closes: list[float], *, volume: float = 1000.0) -> pd.DataFrame:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_value = previous
        high = max(open_value, close) + 0.35
        low = min(open_value, close) - 0.35
        rows.append((open_value, high, low, close, volume + index))
        previous = close
    return pd.DataFrame(
        rows,
        columns=["Open", "High", "Low", "Close", "Volume"],
    )


def test_cluster_rank_is_touches_then_recency() -> None:
    cluster = sc._strong_cluster(
        [
            (5, 100.0),
            (10, 100.1),
            (20, 110.0),
            (21, 110.1),
            (22, 109.9),
        ],
        current_index=25,
        tolerance=0.25,
        minimum_touches=2,
        maximum_age_bars=300,
        stored=40,
        kind="resistance",
    )
    assert cluster is not None
    assert cluster["touches"] == 3
    assert 109.9 <= cluster["level"] <= 110.1


def test_cluster_break_has_priority_over_pivot_break() -> None:
    frame = _frame([99.0] * 15 + [100.0, 101.5])
    result = sc._event_contract(
        frame,
        support_cluster={"low": 95.0, "high": 95.2, "level": 95.1},
        resistance_cluster={"low": 100.0, "high": 100.2, "level": 100.1},
        last_low=96.0,
        last_high=100.0,
        structure_direction=1,
        atr_value=1.0,
        params=sc._params("1d"),
    )
    assert result["selected"]["source"] == "sr_cluster"
    assert result["selected"]["priority"] == 240


def test_cluster_retest_has_priority_over_pivot_retest() -> None:
    frame = _frame([99.0] * 8 + [100.8, 101.0, 100.4, 100.5])
    frame.loc[len(frame) - 1, "Low"] = 100.05
    result = sc._event_contract(
        frame,
        support_cluster={"low": 95.0, "high": 95.2, "level": 95.1},
        resistance_cluster={"low": 100.0, "high": 100.2, "level": 100.1},
        last_low=96.0,
        last_high=100.0,
        structure_direction=1,
        atr_value=1.0,
        params=sc._params("1d"),
    )
    assert result["selected"]["code"] == "CLUSTER_RETEST_UP"
    assert result["selected"]["priority"] == 340


def test_role_reversal_fails_on_close_back_through_cluster() -> None:
    frame = _frame([99.0] * 8 + [100.8, 101.0, 99.6])
    state = sc._role_state(
        frame,
        {"low": 100.0, "high": 100.2, "level": 100.1},
        direction=1,
        buffer=0.05,
        retest_window=8,
        tolerance=0.15,
    )
    assert state["broken_recently"] is True
    assert state["failed"] is True
    assert state["retest"] is False


def test_stop_uses_protective_cluster_before_pivot() -> None:
    frame = _frame([104.0] * 20 + [105.0])
    plan = sc._risk_plan(
        frame,
        direction=1,
        atr_value=2.0,
        event={"code": "PIVOT_BOS_UP", "direction": 1},
        support_cluster={"low": 102.0, "high": 102.2, "level": 102.1},
        resistance_cluster={"low": 108.0, "high": 108.2, "level": 108.1},
        highs=[(5, 108.0), (10, 112.0), (15, 116.0)],
        lows=[(4, 103.0), (9, 103.5)],
        last_high=104.5,
        last_low=103.5,
        zone=None,
        range_high=110.0,
        range_low=100.0,
        params=sc._params("1d"),
        qualified=True,
    )
    assert plan["valid"] is True
    assert plan["stop_source"] == "protective_support_cluster"
    assert math.isclose(plan["stop"], 101.5)


def test_targets_use_cluster_then_new_independent_pivots() -> None:
    frame = _frame([104.0] * 20 + [105.0])
    plan = sc._risk_plan(
        frame,
        direction=1,
        atr_value=2.0,
        event={"code": "CLUSTER_RETEST_UP", "direction": 1},
        support_cluster={"low": 103.0, "high": 103.2, "level": 103.1},
        resistance_cluster={"low": 108.0, "high": 108.2, "level": 108.1},
        highs=[(5, 108.0), (10, 112.0), (15, 116.0)],
        lows=[(4, 103.0), (9, 103.5)],
        last_high=104.5,
        last_low=103.5,
        zone=None,
        range_high=118.0,
        range_low=100.0,
        params=sc._params("1d"),
        qualified=True,
    )
    assert plan["valid"] is True
    assert plan["target_sources"] == [
        "opposing_sr_cluster",
        "new_confirmed_pivot_t2",
        "new_confirmed_pivot_t3",
    ]
    assert plan["targets"] == sorted(plan["targets"])


def test_near_opposing_cluster_blocks_unbroken_plan() -> None:
    veto = sc._opposition_veto(
        direction=1,
        price=100.0,
        atr_value=2.0,
        event={
            "code": "EARLY_SWEEP_UP",
            "direction": 1,
            "source": "pivot",
            "trigger": "confirmed_recovery_close",
        },
        support_cluster=None,
        resistance_cluster={"low": 101.0, "high": 101.2, "level": 101.1},
    )
    assert veto["blocked"] is True


def test_volume_is_price_first_for_forex() -> None:
    frame = _frame(
        [100.0 + math.sin(index / 3) for index in range(40)],
        volume=0.0,
    )
    volume = sc._volume_context(
        frame,
        asset_class="forex",
        market="FOREX",
    )
    assert volume["policy"] == "price_first"
    assert volume["trusted"] is False
