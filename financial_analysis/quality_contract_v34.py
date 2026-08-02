"""SC-FQ3.4 inspired, timeframe-invariant financial quality contract.

This module scores business quality only from completed annual/quarterly
financial metrics. Market valuation is reported separately and never changes
the business-quality score. Missing metrics do not receive zero points; they
reduce coverage and therefore confidence.
"""
from __future__ import annotations

import math
from typing import Any, Mapping

QUALITY_CONTRACT_VERSION = "SC-FQ3.4-PY"


def _finite(value: Any, *, zero_is_missing: bool = False) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(number):
        return None
    if zero_is_missing and abs(number) <= 1e-12:
        return None
    return number


def _first(metrics: Mapping[str, Any], *keys: str, zero_is_missing: bool = False) -> float | None:
    for key in keys:
        if key not in metrics:
            continue
        value = _finite(metrics.get(key), zero_is_missing=zero_is_missing)
        if value is not None:
            return value
    return None


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return min(maximum, max(minimum, value))


def _positive_score(value: float | None, bad: float, good: float) -> float | None:
    if value is None:
        return None
    return 100.0 * _clamp((value - bad) / max(good - bad, 1e-12))


def _inverse_score(value: float | None, good: float, bad: float) -> float | None:
    if value is None:
        return None
    return 100.0 * _clamp((bad - value) / max(bad - good, 1e-12))


def _profile(value: Any, metrics: Mapping[str, Any]) -> str:
    requested = str(value or "").strip().lower()
    if requested in {"bank", "banks", "banking", "بنك", "بنوك"}:
        return "bank"
    if requested in {"insurance", "insurer", "تأمين"}:
        return "insurance"
    if requested in {"general", "عام"}:
        return "general"
    industry = " ".join(
        str(metrics.get(key) or "")
        for key in ("Industry", "industry", "Sector", "sector", "Company_Type")
    ).lower()
    if "bank" in industry or "بنك" in industry:
        return "bank"
    if "insurance" in industry or "تأمين" in industry:
        return "insurance"
    return "general"


def _reported_data_quality(metrics: Mapping[str, Any]) -> dict[str, Any]:
    passed = metrics.get("Data_Quality_Pass")
    score = _finite(metrics.get("Data_Quality_Score"))
    issues = [str(item) for item in metrics.get("Data_Quality_Issues") or []]
    if passed is None:
        passed = score is None or score >= 50
    return {
        "pass": bool(passed),
        "score": int(_clamp((score or 0.0) / 100.0) * 100) if score is not None else None,
        "issues": issues,
    }


def build_financial_quality_contract(
    metrics: Mapping[str, Any] | None,
    *,
    profile: str | None = None,
) -> dict[str, Any]:
    """Return quality, coverage, independent risk flags and valuation context."""
    source = dict(metrics or {})
    company_profile = _profile(profile, source)
    specialized = company_profile in {"bank", "insurance"}

    roe = _first(source, "ROE", "Return_on_Equity", "return_on_equity")
    roic = _first(source, "ROIC", "Return_on_Invested_Capital", "return_on_invested_capital")
    operating_margin = _first(source, "Operating_Margin", "operating_margin")
    revenue_growth = _first(source, "Revenue_Growth_YoY", "revenue_growth", "Revenue_Growth")
    eps_growth = _first(source, "EPS_Growth_YoY", "eps_growth", "NetIncome_Growth_YoY")
    cash_conversion = _first(source, "OCF_to_NetIncome", "cash_conversion")
    fcf_margin = _first(source, "FCF_Margin", "fcf_margin")
    debt_to_equity = _first(source, "Debt_to_Equity", "debt_to_equity")
    current_ratio = _first(source, "Current_Ratio", "current_ratio")
    share_growth = _first(source, "Share_Growth_YoY", "share_growth", "Shares_Growth")
    piotroski = _first(source, "Piotroski_Score", "piotroski")
    altman = _first(source, "Altman_Z", "altman")
    beneish = _first(source, "Beneish_M", "Beneish_M_Score", "beneish")
    pe = _first(source, "PE_Trailing", "PE", "pe", zero_is_missing=True)
    pb = _first(source, "PB", "Price_to_Book", "pb", zero_is_missing=True)
    net_income = _first(source, "Net_Income", "net_income")
    operating_cash = _first(source, "Operating_Cash_Flow", "operating_cash_flow")
    free_cash = _first(source, "Free_Cash_Flow", "free_cash_flow")

    thresholds = {
        "roe_good": 0.16 if company_profile == "bank" else 0.18 if company_profile == "insurance" else 0.22,
        "margin_good": 0.16 if specialized else 0.25,
    }
    metric_scores: dict[str, float | None] = {
        "profitability": _positive_score(roe, 0.0, thresholds["roe_good"]),
        "return_on_capital": None if specialized else _positive_score(roic, 0.0, 0.18),
        "operating_margin": _positive_score(operating_margin, 0.0, thresholds["margin_good"]),
        "revenue_growth": _positive_score(revenue_growth, -0.05, 0.20),
        "earnings_growth": _positive_score(eps_growth, -0.10, 0.25),
        "cash_conversion": _positive_score(cash_conversion, 0.50, 1.20),
        "free_cash_flow": _positive_score(fcf_margin, -0.02, 0.12),
        "leverage": None if company_profile == "bank" else _inverse_score(debt_to_equity, 0.30, 2.50 if company_profile == "insurance" else 2.00),
        "liquidity": None if company_profile == "bank" else _positive_score(current_ratio, 0.70, 2.00),
        "dilution": _inverse_score(share_growth, -0.02, 0.10),
        "piotroski": _positive_score(piotroski, 3.0, 8.0),
        "altman": None if specialized else _positive_score(altman, 1.0, 3.0),
        "beneish": _inverse_score(beneish, -2.50, -1.20),
    }
    weights = {
        "profitability": 14.0,
        "return_on_capital": 0.0 if specialized else 10.0,
        "operating_margin": 6.0 if specialized else 9.0,
        "revenue_growth": 8.0,
        "earnings_growth": 8.0,
        "cash_conversion": 5.0 if specialized else 10.0,
        "free_cash_flow": 4.0 if specialized else 8.0,
        "leverage": 8.0,
        "liquidity": 5.0,
        "dilution": 5.0,
        "piotroski": 6.0,
        "altman": 4.0,
        "beneish": 3.0,
    }
    applicable_weight = sum(
        weight
        for name, weight in weights.items()
        if weight > 0
        and not (company_profile == "bank" and name in {"leverage", "liquidity"})
        and not (specialized and name == "altman")
    )
    available_weight = 0.0
    weighted_sum = 0.0
    for name, score in metric_scores.items():
        weight = weights[name]
        if score is None or weight <= 0:
            continue
        available_weight += weight
        weighted_sum += score * weight
    completeness = 100.0 * available_weight / applicable_weight if applicable_weight > 0 else 0.0
    raw_quality = weighted_sum / available_weight if available_weight > 0 else None
    coverage_factor = _clamp(completeness / 75.0)
    coverage_adjusted = raw_quality * (0.70 + 0.30 * coverage_factor) if raw_quality is not None else None

    flags: list[dict[str, Any]] = []
    if net_income is not None and net_income < 0:
        flags.append({"axis": "profitability", "code": "negative_net_income", "penalty": 6.0})
    cash_risk = (
        (operating_cash is not None and operating_cash < 0)
        or (free_cash is not None and free_cash < 0)
        or (cash_conversion is not None and cash_conversion < 0.50)
    )
    if cash_risk:
        flags.append({"axis": "cash_generation", "code": "weak_cash_generation", "penalty": 6.0})
    if share_growth is not None and share_growth > 0.08:
        flags.append({"axis": "dilution", "code": "material_share_dilution", "penalty": 6.0})
    if not specialized and (
        (debt_to_equity is not None and debt_to_equity > 2.0)
        or (altman is not None and altman < 1.0)
    ):
        flags.append({"axis": "solvency", "code": "solvency_risk", "penalty": 6.0})
    if beneish is not None and beneish > -1.20:
        flags.append({"axis": "reporting", "code": "beneish_reporting_risk", "penalty": 6.0})
    red_flag_penalty = min(len(flags), 4) * 6.0
    quality_score = max(0.0, coverage_adjusted - red_flag_penalty) if coverage_adjusted is not None else None

    data_quality = _reported_data_quality(source)
    if completeness < 60:
        grade = "بيانات غير كافية"
    elif specialized:
        grade = "مؤشرات أولية قطاعية"
    elif quality_score is None:
        grade = "غير متاح"
    elif quality_score >= 80 and completeness >= 75 and not flags:
        grade = "جودة قوية"
    elif quality_score >= 65:
        grade = "جودة جيدة"
    elif quality_score >= 50:
        grade = "جودة متوسطة"
    else:
        grade = "جودة ضعيفة"

    valuation_scores = {
        "pe": _inverse_score(pe, 10.0, 35.0) if pe is not None and pe > 0 else None,
        "pb": _inverse_score(pb, 1.0 if company_profile == "bank" else 1.2, 3.0 if company_profile == "bank" else 5.0) if pb is not None and pb > 0 else None,
    }
    valuation_available = [value for value in valuation_scores.values() if value is not None]
    valuation_score = sum(valuation_available) / len(valuation_available) if valuation_available else None
    valuation_grade = (
        "غير متاح"
        if valuation_score is None
        else "جذاب"
        if valuation_score >= 70
        else "مقبول"
        if valuation_score >= 40
        else "مرتفع"
    )

    warnings: list[str] = []
    if not data_quality["pass"]:
        warnings.append("بوابة جودة البيانات الأصلية لم تجتز الفحص")
    if completeness < 60:
        warnings.append("تغطية المقاييس أقل من 60%؛ لا يعتمد الحكم منفردًا")
    elif completeness < 75:
        warnings.append("بعض المقاييس المالية غير متاحة وخُفضت الثقة")
    if specialized:
        warnings.append("البنوك والتأمين تحتاج مؤشرات قطاعية متخصصة إضافية")
    warnings.extend(str(item) for item in data_quality["issues"][:8])

    return {
        "ok": quality_score is not None and completeness >= 60 and data_quality["pass"],
        "version": QUALITY_CONTRACT_VERSION,
        "profile": company_profile,
        "period_invariant": True,
        "quality_excludes_valuation": True,
        "quality_score": round(quality_score, 2) if quality_score is not None else None,
        "raw_quality_score": round(raw_quality, 2) if raw_quality is not None else None,
        "grade": grade,
        "completeness": round(completeness, 2),
        "available_weight": round(available_weight, 2),
        "applicable_weight": round(applicable_weight, 2),
        "metric_scores": {key: round(value, 2) if value is not None else None for key, value in metric_scores.items()},
        "risk_flags": flags,
        "red_flag_penalty": red_flag_penalty,
        "valuation": {
            "score": round(valuation_score, 2) if valuation_score is not None else None,
            "grade": valuation_grade,
            "pe": pe,
            "pb": pb,
            "metric_scores": valuation_scores,
        },
        "data_quality": data_quality,
        "warnings": list(dict.fromkeys(warnings)),
        "source_period": source.get("Data_Period_Used") or "Annual/Quarterly completed statements",
    }


def attach_financial_quality_contract(metrics: Mapping[str, Any] | None, *, profile: str | None = None) -> dict[str, Any]:
    output = dict(metrics or {})
    contract = build_financial_quality_contract(output, profile=profile)
    output["SC_FQ3_4"] = contract
    output["Quality_Score_100"] = contract.get("quality_score")
    output["Quality_Grade"] = contract.get("grade")
    output["Quality_Completeness"] = contract.get("completeness")
    output["Valuation_Score_100"] = (contract.get("valuation") or {}).get("score")
    output["Valuation_Grade"] = (contract.get("valuation") or {}).get("grade")
    output["Financial_Risk_Flags"] = list(contract.get("risk_flags") or [])
    return output


__all__ = [
    "QUALITY_CONTRACT_VERSION",
    "attach_financial_quality_contract",
    "build_financial_quality_contract",
]
