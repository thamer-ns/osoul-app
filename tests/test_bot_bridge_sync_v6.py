from __future__ import annotations

from dataclasses import dataclass

from ai_engine_core import bot_bridge_v5 as bridge


@dataclass(frozen=True)
class _Tenant:
    user_id: int = 123
    portfolio_id: int = 456


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


def test_sync_channel_is_opaque_and_does_not_send_raw_tenant_ids(monkeypatch):
    monkeypatch.setattr(bridge, "current_tenant", lambda: _Tenant())
    monkeypatch.setattr(
        bridge,
        "_secret",
        lambda name: "s" * 40 if name == "SC_BOT_SYNC_SECRET" else "",
    )

    channel = bridge._sync_channel()

    assert len(channel) == 64
    assert all(character in "0123456789abcdef" for character in channel)
    assert "123" not in channel
    assert "456" not in channel


def test_public_bot_url_requires_https_but_local_development_http_is_allowed(monkeypatch):
    values = {
        "SC_BOT_BASE_URL": "http://bot.example",
        "OSOUL_ALLOW_INSECURE_BOT_HTTP": "0",
    }
    monkeypatch.setattr(bridge, "_secret", lambda name: values.get(name, ""))
    assert bridge._base_url() == ""

    values["SC_BOT_BASE_URL"] = "http://localhost:8000"
    assert bridge._base_url() == "http://localhost:8000"

    values["SC_BOT_BASE_URL"] = "https://bot.example"
    assert bridge._base_url() == "https://bot.example"


def test_sync_pulls_events_in_order_and_advances_cursor(monkeypatch):
    saved = []
    recorded = []
    events = [
        {"id": 11, "payload": {"e": "NL"}},
        {"id": 12, "payload": {"e": "T1"}},
    ]

    class _Requests:
        @staticmethod
        def get(url, *, headers, params, timeout):
            assert url.endswith("/integrations/osoli/events")
            assert headers["X-Osoli-Sync-Token"] == "token"
            assert len(headers["X-Osoli-Sync-Channel"]) == 64
            assert params == {"after": 10, "limit": 100}
            assert timeout == 12
            return _Response({"ok": True, "events": events, "has_more": False})

    monkeypatch.setattr(bridge, "requests", _Requests)
    monkeypatch.setattr(bridge, "_base_url", lambda: "https://bot.example")
    monkeypatch.setattr(
        bridge,
        "_sync_headers",
        lambda: {
            "X-Osoli-Sync-Token": "token",
            "X-Osoli-Sync-Channel": "a" * 64,
        },
    )
    monkeypatch.setattr(bridge, "_sync_channel", lambda: "a" * 64)
    monkeypatch.setattr(bridge, "load_cursor", lambda channel: 10)
    monkeypatch.setattr(
        bridge,
        "save_cursor",
        lambda channel, cursor: saved.append((channel, cursor)) or True,
    )

    def fake_record(payload, *, remote_event_id, remote_channel):
        recorded.append((payload["e"], remote_event_id, remote_channel))
        return {"ok": True, "created": True}

    monkeypatch.setattr(bridge, "record_external_event", fake_record)
    monkeypatch.setattr(bridge, "quarantine_remote_event", lambda *args: {"ok": True})

    result = bridge.sync_bot_events(limit=100)

    assert result == {
        "ok": True,
        "reason": None,
        "received": 2,
        "duplicates": 0,
        "quarantined": 0,
        "rejected": 0,
        "cursor": 12,
        "has_more": False,
    }
    assert recorded == [("NL", 11, "a" * 64), ("T1", 12, "a" * 64)]
    assert saved == [("a" * 64, 12)]


def test_rejected_event_is_quarantined_and_does_not_block_later_events(monkeypatch):
    saved = []
    quarantined = []

    class _Requests:
        @staticmethod
        def get(*args, **kwargs):
            return _Response(
                {
                    "events": [
                        {"id": 21, "payload": {"e": "NL"}},
                        {"id": 22, "payload": {"e": "T3"}},
                        {"id": 23, "payload": {"e": "T1"}},
                    ],
                    "has_more": False,
                }
            )

    monkeypatch.setattr(bridge, "requests", _Requests)
    monkeypatch.setattr(bridge, "_base_url", lambda: "https://bot.example")
    monkeypatch.setattr(bridge, "_sync_headers", lambda: {"token": "configured"})
    monkeypatch.setattr(bridge, "_sync_channel", lambda: "b" * 64)
    monkeypatch.setattr(bridge, "load_cursor", lambda channel: 20)
    monkeypatch.setattr(
        bridge,
        "save_cursor",
        lambda channel, cursor: saved.append(cursor) or True,
    )

    def fake_record(payload, **kwargs):
        if payload["e"] == "T3":
            return {
                "ok": False,
                "created": False,
                "reason": "invalid_lifecycle_transition",
            }
        return {"ok": True, "created": True}

    def fake_quarantine(channel, remote_id, item, reason):
        quarantined.append((channel, remote_id, reason))
        return {"ok": True, "created": True}

    monkeypatch.setattr(bridge, "record_external_event", fake_record)
    monkeypatch.setattr(bridge, "quarantine_remote_event", fake_quarantine)

    result = bridge.sync_bot_events()

    assert result["ok"] is True
    assert result["reason"] == "completed_with_quarantine"
    assert result["received"] == 2
    assert result["quarantined"] == 1
    assert result["rejected"] == 0
    assert result["cursor"] == 23
    assert saved == [23]
    assert quarantined == [("b" * 64, 22, "invalid_lifecycle_transition")]
