from financial_analysis.quality_contract_v34 import build_financial_quality_contract


def _sample():
    return {
        "Data_Quality_Pass": True,
        "Data_Quality_Score": 90,
        "ROE": 0.20,
        "ROIC": 0.17,
        "Operating_Margin": 0.22,
        "Revenue_Growth_YoY": 0.15,
        "EPS_Growth_YoY": 0.18,
        "OCF_to_NetIncome": 1.10,
        "FCF_Margin": 0.10,
        "Debt_to_Equity": 0.50,
        "Current_Ratio": 1.8,
        "Share_Growth_YoY": 0.0,
        "Piotroski_Score": 8,
        "Altman_Z": 3.2,
        "Beneish_M": -2.5,
        "PE_Trailing": 15.0,
        "PB": 2.0,
        "Net_Income": 100.0,
        "Operating_Cash_Flow": 120.0,
        "Free_Cash_Flow": 80.0,
    }


def test_price_multiples_do_not_change_quality_score():
    first = _sample()
    second = _sample()
    second.update({"PE_Trailing": 80.0, "PB": 12.0})
    a = build_financial_quality_contract(first)
    b = build_financial_quality_contract(second)
    assert a["quality_score"] == b["quality_score"]
    assert a["valuation"]["score"] != b["valuation"]["score"]


def test_missing_values_reduce_coverage():
    result = build_financial_quality_contract(
        {
            "Data_Quality_Pass": True,
            "Data_Quality_Score": 80,
            "ROE": 0.18,
            "Piotroski_Score": 7,
        }
    )
    assert result["metric_scores"]["return_on_capital"] is None
    assert result["completeness"] < 60
    assert result["ok"] is False


def test_source_quality_failure_blocks_ok():
    values = _sample()
    values["Data_Quality_Pass"] = False
    values["Data_Quality_Issues"] = ["incomplete statement"]
    result = build_financial_quality_contract(values)
    assert result["ok"] is False
    assert "incomplete statement" in result["warnings"]
