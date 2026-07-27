from __future__ import annotations

import json

import numpy as np

from ai_engine_core.json_utils import strict_json_dumps


def test_strict_json_replaces_non_finite_numbers():
    payload = {
        "nan": float("nan"),
        "positive_infinity": float("inf"),
        "numpy": np.float64("-inf"),
        "nested": [1.0, float("nan")],
    }
    encoded = strict_json_dumps(payload)
    decoded = json.loads(encoded)
    assert decoded == {
        "nan": None,
        "positive_infinity": None,
        "numpy": None,
        "nested": [1.0, None],
    }
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
