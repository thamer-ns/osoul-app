"""Backward-compatible import path for the atomic tenant journal v7."""
from __future__ import annotations

from .external_signal_journal_v7 import (
    JournalStateError,
    QUARANTINE_TABLE,
    STATE_TABLE,
    TABLE,
    install_external_signal_journal,
    latest_external_event,
    latest_remote_cursor,
    lifecycle_snapshot,
    quarantine_remote_event,
    recent_external_events,
    recent_quarantined_events,
    record_external_event,
)

__all__ = [
    "JournalStateError",
    "QUARANTINE_TABLE",
    "STATE_TABLE",
    "TABLE",
    "install_external_signal_journal",
    "latest_external_event",
    "latest_remote_cursor",
    "lifecycle_snapshot",
    "quarantine_remote_event",
    "recent_external_events",
    "recent_quarantined_events",
    "record_external_event",
]
