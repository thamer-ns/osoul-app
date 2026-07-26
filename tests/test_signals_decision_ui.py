import math

from views.signals import _decision_fields, _entry_text, _recommendation_kind, _safe_number


def test_recommendation_kind_understands_arabic_bull_and_bear_wording():
    assert _recommendation_kind("فرصة صاعدة") == "buy"
    assert _recommendation_kind("خروج أو تحوط بسبب اتجاه هابط") == "sell"
    assert _recommendation_kind("مراقبة", direction="sell") == "sell"


def test_safe_number_rejects_nan_and_infinity():
    assert _safe_number(float("nan"), 7.0) == 7.0
    assert _safe_number(float("inf"), 8.0) == 8.0
    assert math.isfinite(_safe_number("12.5"))


def test_decision_fields_recover_central_decision_from_raw_report():
    extracted = {
        "raw": {
            "direction": "buy",
            "direction_score": 64.5,
            "lifecycle_status": "ACTIONABLE",
            "opportunity_label": "اختراق قوي",
            "decision_engine": {
                "plan": {
                    "plan_id": "abc123",
                    "entry_low": 99,
                    "entry_high": 101,
                    "entry": 100,
                }
            },
        }
    }

    fields = _decision_fields(extracted)

    assert fields["direction"] == "buy"
    assert fields["direction_score"] == 64.5
    assert fields["lifecycle"] == "ACTIONABLE"
    assert fields["opportunity"] == "اختراق قوي"
    assert fields["plan_id"] == "abc123"
    assert _entry_text(extracted, fields["plan"]) == "99.00 – 101.00"
