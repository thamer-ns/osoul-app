from __future__ import annotations

import math
import random

import pandas as pd

from ai_engine_core import sc_feature_pack_v925 as sc


def _frame(closes: list[float], *, volume: float = 1000.0) -> pd.DataFrame:
    rows = []
    previous = closes[0]
    for index, close in enumerate(closes):
        open_value = previous
        rows.append(
            (
                open_value,
                max(open_value, close) + 0.35,
                min(open_value, close) - 0.35,
                close,
                volume + index,
            )
        )
        previous = close
    return pd.DataFrame(
        rows,
        columns=["Open", "High", "Low", "Close", "Volume"],
    )


def _market_frame(
    rows: int = 900,
    *,
    seed: int = 7,
    drift: float = 0.02,
) -> pd.DataFrame:
    random.seed(seed)
    price = 100.0
    data = []
    for index in range(rows):
        wave = math.sin(index / 8.0) * 0.35
        move = drift + wave * 0.08 + random.uniform(-0.55, 0.55)
        open_value = price
        close = max(1.0, price + move)
        high = max(open_value, close) + random.uniform(0.15, 0.65)
        low = min(open_value, close) - random.uniform(0.15, 0.65)
        volume = 1000.0 + 250.0 * abs(math.sin(index / 11.0)) + index % 13
        data.append((open_value, high, low, close, volume))
        price = close
    return pd.DataFrame(
        data,
        columns=["Open", "High", "Low", "Close", "Volume"],
    )


def test_broken_resistance_is_current_support() -> None:
    clusters = [
        {
            "kind": "resistance",
            "origin_kind": "resistance",
            "low": 99.8,
            "high": 100.2,
            "level": 100.0,
            "touches": 3,
            "recent_bar": 20,
            "age_bars": 5,
            "member_bars": (4, 12, 20),
        }
    ]
    supports = sc._select_current_role_clusters(
        clusters,
        price=104.0,
        tolerance=0.2,
        atr_value=2.0,
        role="support",
    )
    resistances = sc._select_current_role_clusters(
        clusters,
        price=104.0,
        tolerance=0.2,
        atr_value=2.0,
        role="resistance",
    )
    assert len(supports) == 1
    assert supports[0]["role_reversed"] is True
    assert supports[0]["kind"] == "support"
    assert not resistances


def test_broken_support_is_current_resistance() -> None:
    clusters = [
        {
            "kind": "support",
            "origin_kind": "support",
            "low": 99.8,
            "high": 100.2,
            "level": 100.0,
            "touches": 3,
            "recent_bar": 20,
            "age_bars": 5,
            "member_bars": (4, 12, 20),
        }
    ]
    resistances = sc._select_current_role_clusters(
        clusters,
        price=96.0,
        tolerance=0.2,
        atr_value=2.0,
        role="resistance",
    )
    assert len(resistances) == 1
    assert resistances[0]["role_reversed"] is True
    assert resistances[0]["kind"] == "resistance"


def test_stale_resistance_below_price_does_not_veto_long() -> None:
    veto = sc._opposition_veto(
        direction=1,
        price=105.0,
        atr_value=2.0,
        event=None,
        support_cluster=None,
        resistance_cluster={"low": 100.0, "high": 100.2, "level": 100.1},
    )
    assert veto["blocked"] is False


def test_integrity_rejects_inverted_levels() -> None:
    result = sc._integrity(
        price=100.0,
        support={"low": 101.0, "high": 101.2, "level": 101.1},
        resistance={"low": 99.0, "high": 99.2, "level": 99.1},
        plan={"valid": False},
    )
    assert result["ok"] is False
    assert "support_above_price" in result["issues"]
    assert "resistance_below_price" in result["issues"]


def test_role_reversal_requires_close_to_hold() -> None:
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


def test_stop_and_targets_are_direction_safe() -> None:
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
    assert plan["stop"] < plan["entry"] < min(plan["targets"])
    assert plan["target_sources"] == [
        "opposing_sr_cluster",
        "new_confirmed_pivot_t2",
        "new_confirmed_pivot_t3",
    ]


def test_randomized_pack_never_exports_inverted_levels() -> None:
    for seed in range(12):
        pack = sc.build_sc_feature_pack(
            _market_frame(seed=seed, drift=(seed % 3 - 1) * 0.015),
            interval="1d",
            asset_class="stock",
            market="SAUDI",
        )
        assert pack["ok"] is True
        assert pack["integrity"]["ok"] is True
        price = float(pack["price"])
        support = pack["sr"]["support"]
        resistance = pack["sr"]["resistance"]
        if support:
            assert float(support["low"]) <= price
            assert support["kind"] == "support"
        if resistance:
            assert float(resistance["high"]) >= price
            assert resistance["kind"] == "resistance"


def test_supported_timeframes_keep_level_integrity() -> None:
    frame = _market_frame()
    for interval in ("1m", "5m", "15m", "30m", "1h", "4h", "1d", "1w", "1mo"):
        pack = sc.build_sc_feature_pack(
            frame,
            interval=interval,
            asset_class="stock",
            market="SAUDI",
        )
        assert pack["ok"] is True, interval
        assert pack["integrity"]["ok"] is True, interval
        assert pack["indicator_contract"] == sc.SC_INDICATOR_CONTRACT
