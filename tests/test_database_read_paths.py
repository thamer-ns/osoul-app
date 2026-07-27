from __future__ import annotations

import pandas as pd

import database


def test_fetch_table_engine_path_does_not_acquire_raw_connection(monkeypatch):
    engine = object()
    calls = []
    monkeypatch.setattr(database, "_get_db_kind", lambda: "postgres")
    monkeypatch.setattr(database, "_get_engine", lambda: engine)
    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("raw pool should not be used")),
    )

    def fake_read_sql(query, connection, *args, **kwargs):
        calls.append((str(query), connection))
        return pd.DataFrame(columns=["id"])

    monkeypatch.setattr(database.pd, "read_sql", fake_read_sql)
    result = database.fetch_table("trades")
    assert result.empty
    assert calls == [("SELECT * FROM trades", engine)]


def test_fetch_df_engine_path_does_not_acquire_raw_connection(monkeypatch):
    engine = object()
    monkeypatch.setattr(database, "_get_db_kind", lambda: "postgres")
    monkeypatch.setattr(database, "_get_engine", lambda: engine)
    monkeypatch.setattr(
        database,
        "get_connection",
        lambda: (_ for _ in ()).throw(AssertionError("raw pool should not be used")),
    )
    monkeypatch.setattr(
        database.pd,
        "read_sql",
        lambda query, connection, *args, **kwargs: pd.DataFrame([{"x": 1}]),
    )
    result = database.fetch_df("SELECT 1 AS x")
    assert result.iloc[0]["x"] == 1
