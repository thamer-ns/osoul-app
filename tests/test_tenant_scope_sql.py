from tenant_scope import scoped_sql_preview


def test_insert_receives_tenant_columns():
    query, params = scoped_sql_preview(
        "INSERT INTO trades (symbol, quantity) VALUES (%s,%s)",
        ("1120.SR", 10),
    )
    assert "user_id" in query
    assert "portfolio_id" in query
    assert params[-2:] == (7, 11)


def test_update_is_restricted_to_active_portfolio():
    query, params = scoped_sql_preview(
        "UPDATE trades SET quantity=%s WHERE id=%s",
        (5, 99),
    )
    assert "user_id=%s" in query
    assert "portfolio_id=%s" in query
    assert params == (5, 99, 7, 11)


def test_thesis_conflict_target_is_tenant_scoped():
    query, params = scoped_sql_preview(
        """
        INSERT INTO investmentthesis
            (symbol, thesis_text, target_price, recommendation, last_updated)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (symbol)
        DO UPDATE SET thesis_text=EXCLUDED.thesis_text
        """,
        ("1120.SR", "نص", 50.0, "Hold", "2026-07-26"),
    )
    compact = " ".join(query.split()).lower()
    assert "on conflict (user_id, portfolio_id, symbol)" in compact
    assert params[-2:] == (7, 11)
