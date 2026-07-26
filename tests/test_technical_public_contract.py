import numpy as np
import pandas as pd

from technical_indicators import compute_advanced_technical_pack


def test_public_advanced_pack_has_cache_identity():
    rows = 280
    close = 100 + np.linspace(0, 20, rows)
    frame = pd.DataFrame(
        {
            "Open": close - 0.2,
            "High": close + 0.7,
            "Low": close - 0.7,
            "Close": close,
            "Volume": np.full(rows, 250_000),
        },
        index=pd.date_range("2025-01-01", periods=rows, freq="D"),
    )

    pack = compute_advanced_technical_pack(frame, symbol="1120.SR", timeframe="1d")

    assert pack["name"] == "Advanced Technical Pack v2"
    assert pack["meta"]["schema_version"] == "2.0"
    assert pack["meta"]["confirmation"] == "close"
