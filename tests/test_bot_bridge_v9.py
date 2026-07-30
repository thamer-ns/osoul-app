from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass

from ai_engine_core import bot_bridge_v5 as bridge


@dataclass(frozen=True)
class _Tenant:
    user_id: int = 123
    portfolio_id: int = 456


def test_sync_channel_keeps_the_durable_v6_namespace(monkeypatch):
    secret = "s" * 40
    monkeypatch.setattr(bridge, "current_tenant", lambda: _Tenant())
    monkeypatch.setattr(
        bridge,
        "_secret",
        lambda name: secret if name == "SC_BOT_SYNC_SECRET" else "",
    )

    expected = hmac.new(
        secret.encode(),
        b"osoli-sync-v6:123:456",
        hashlib.sha256,
    ).hexdigest()

    assert bridge._sync_channel() == expected
    assert bridge.bridge_configuration()["sync_channel_contract"] == "stable-v6"


def test_remote_ids_are_validated_before_sorting():
    ordered, rejected = bridge._validated_remote_events(
        [
            {"id": "12", "payload": {}},
            {"id": "not-a-number", "payload": {}},
            {"id": 11, "payload": {}},
            {"id": 0, "payload": {}},
            "bad-row",
        ]
    )

    assert [remote_id for remote_id, _item in ordered] == [11, 12]
    assert rejected == 3


def test_normalized_payload_is_converted_back_to_compact_wire():
    wire = bridge._wire_input(
        {
            "schema_version": 1,
            "source": "SC-V90-D",
            "event": "NL",
            "symbol": "TADAWUL:1120",
            "asset_type": "stock",
            "timeframe": "1d",
            "event_timestamp_ms": 1_760_000_000_000,
            "event_price": 100.0,
            "direction": "buy",
            "direction_code": 1,
            "entry": 100.0,
            "stop": 98.0,
            "targets": [102.0, 104.0, 106.0],
            "target_count": 3,
            "score": 8,
            "score_maximum": 10,
            "confidence": 80.0,
            "counter_trend": False,
            "geometry": {"valid": True},
        }
    )

    assert isinstance(wire, dict)
    assert wire["s"] == "SC-V90-D"
    assert wire["e"] == "NL"
    assert wire["f"] == "1d"
    assert "source" not in wire
