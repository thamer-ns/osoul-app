"""Official financial-statement provider fusion for Osoli v5.

Stored/manual statements remain authoritative.  This module is only called when
local coverage is insufficient.  Remote line items are normalized into the
summary schema consumed by ``financial_analysis.metrics`` and carry explicit
source, period and quality lineage.  Missing values stay missing; zero is never
invented to make a ratio appear available.
"""
from __future__ import annotations

import json
import logging
import math
import os
import time
from functools import lru_cache
from typing import Any, Callable

import pandas as pd

import market_providers_v5 as market_v5

LOGGER = logging.getLogger(__name__)
_DEFAULT_ORDER = ("fmp", "eodhd", "alphavantage")

_CANONICAL_ALIASES: dict[str, tuple[str, ...]] = {
    "revenue": ("revenue", "totalRevenue", "total_revenue", "totalRevenueTTM"),
    "net_income": ("netIncome", "netIncomeApplicableToCommonShares", "net_income", "netIncomeTTM"),
    "gross_profit": ("grossProfit", "gross_profit"),
    "operating_income": ("operatingIncome", "operating_income", "ebit"),
    "interest_expense": ("interestExpense", "interest_expense"),
    "eps": ("eps", "epsdiluted", "reportedEPS", "dilutedEPS"),
    "total_assets": ("totalAssets", "total_assets"),
    "total_liabilities": (
        "totalLiabilities",
        "totalLiabilitiesNetMinorityInterest",
        "total_liabilities",
    ),
    "total_equity": (
        "totalStockholdersEquity",
        "totalShareholderEquity",
        "totalEquity",
        "stockholdersEquity",
        "total_equity",
    ),
    "current_assets": ("totalCurrentAssets", "currentAssets", "current_assets"),
    "current_liabilities": (
        "totalCurrentLiabilities",
        "currentLiabilities",
        "current_liabilities",
    ),
    "long_term_debt": (
        "longTermDebt",
        "longTermDebtNoncurrent",
        "longTermDebtAndCapitalLeaseObligation",
        "long_term_debt",
    ),
    "operating_cash_flow": (
        "operatingCashFlow",
        "totalCashFromOperatingActivities",
        "cashflowFromInvestment",
        "operating_cash_flow",
    ),
    "capex": ("capitalExpenditure", "capitalExpenditures", "capital_expenditure", "capex"),
    "free_cash_flow": ("freeCashFlow", "free_cash_flow"),
    "shares_outstanding": (
        "weightedAverageShsOut",
        "weightedAverageShsOutDil",
        "commonStockSharesOutstanding",
        "sharesOutstanding",
        "shares_outstanding",
    ),
    "cash": (
        "cashAndCashEquivalents",
        "cashAndShortTermInvestments",
        "cashAndCashEquivalentsAtCarryingValue",
    ),
}


def configured_financial_order() -> list[str]:
    raw = market_v5._secret("FINANCIAL_DATA_PROVIDER_ORDER") or os.getenv(
        "FINANCIAL_DATA_PROVIDER_ORDER", ""
    )
    requested = [item.strip().lower() for item in str(raw).split(",") if item.strip()]
    output: list[str] = []
    for provider in requested or _DEFAULT_ORDER:
        if provider in _DEFAULT_ORDER and provider not in output:
            output.append(provider)
    for provider in _DEFAULT_ORDER:
        if provider not in output:
            output.append(provider)
    return output


def _finite(value: Any) -> float | None:
    if value in (None, "", "None", "null", "NaN", "-"):
        return None
    try:
        number = float(str(value).replace(",", ""))
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None


def _first(row: dict[str, Any], names: tuple[str, ...]) -> float | None:
    for name in names:
        if name in row:
            value = _finite(row.get(name))
            if value is not None:
                return value
    lower = {str(key).casefold(): value for key, value in row.items()}
    for name in names:
        value = _finite(lower.get(str(name).casefold()))
        if value is not None:
            return value
    return None


def _date_value(row: dict[str, Any]) -> str:
    for name in ("date", "fillingDate", "filingDate", "fiscalDateEnding", "as_of", "Date"):
        value = str(row.get(name) or "").strip()
        if value:
            parsed = pd.to_datetime(value, errors="coerce")
            if pd.notna(parsed):
                return str(parsed.date())
    return ""


def _merge_period_rows(*collections: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for collection in collections:
        for row in collection or []:
            if not isinstance(row, dict):
                continue
            date = _date_value(row)
            if not date:
                continue
            target = merged.setdefault(date, {"date": date})
            for key, value in row.items():
                if value not in (None, ""):
                    target[key] = value
    return list(merged.values())


def _normalize_rows(
    rows: list[dict[str, Any]],
    *,
    source: str,
    period_type: str,
    currency: str | None = None,
) -> pd.DataFrame:
    output: list[dict[str, Any]] = []
    for row in rows:
        date = _date_value(row)
        if not date:
            continue
        normalized: dict[str, Any] = {
            "date": date,
            "date_str": date,
            "period_type": period_type,
            "source": source,
            "currency": str(row.get("reportedCurrency") or row.get("currency") or currency or ""),
        }
        for canonical, aliases in _CANONICAL_ALIASES.items():
            normalized[canonical] = _first(row, aliases)
        if normalized.get("free_cash_flow") is None:
            ocf = normalized.get("operating_cash_flow")
            capex = normalized.get("capex")
            if ocf is not None and capex is not None:
                normalized["free_cash_flow"] = float(ocf) - abs(float(capex))
        output.append(normalized)
    if not output:
        return pd.DataFrame()
    frame = pd.DataFrame(output)
    frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
    frame = frame.dropna(subset=["date"]).sort_values("date", ascending=False)
    frame["date_str"] = frame["date"].dt.date.astype(str)
    return frame.reset_index(drop=True)


def assess_summary_quality(frame: pd.DataFrame) -> dict[str, Any]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {"pass": False, "score": 0, "issues": ["empty"], "periods": 0}
    essential = (
        "revenue",
        "net_income",
        "total_assets",
        "total_liabilities",
        "total_equity",
        "operating_cash_flow",
    )
    issues: list[str] = []
    missing_columns = [column for column in essential if column not in frame.columns]
    if missing_columns:
        issues.append("missing_columns:" + ",".join(missing_columns))
    latest = frame.iloc[0]
    missing_latest = [
        column
        for column in essential
        if column not in frame.columns or _finite(latest.get(column)) is None
    ]
    if missing_latest:
        issues.append("missing_latest:" + ",".join(missing_latest))
    if len(frame) < 2:
        issues.append("insufficient_periods")
    assets = _finite(latest.get("total_assets"))
    liabilities = _finite(latest.get("total_liabilities"))
    equity = _finite(latest.get("total_equity"))
    balance_gap = None
    if assets and liabilities is not None and equity is not None:
        balance_gap = abs(assets - (liabilities + equity)) / abs(assets)
        if balance_gap > 0.20:
            issues.append("balance_sheet_gap")
    score = 100
    score -= min(45, len(missing_latest) * 8)
    score -= 20 if len(frame) < 2 else 0
    score -= 15 if "balance_sheet_gap" in issues else 0
    score -= min(20, len(missing_columns) * 5)
    score = max(0, min(100, score))
    return {
        "pass": score >= 55 and not missing_columns and len(frame) >= 2,
        "score": int(score),
        "issues": issues,
        "periods": int(len(frame)),
        "balance_gap": balance_gap,
        "source": str(latest.get("source") or ""),
        "currency": str(latest.get("currency") or ""),
    }


def _fmp_statements(symbol: str, period_type: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    key = market_v5._secret("FMP_API_KEY")
    resolved = market_v5.resolve_fmp_symbol(symbol)
    if not key or not resolved:
        return pd.DataFrame(), {"reason": "not_configured_or_unresolved"}
    period = "annual" if period_type == "Annual" else "quarter"
    endpoints = {
        "income": "income-statement",
        "balance": "balance-sheet-statement",
        "cash": "cash-flow-statement",
    }
    payloads: dict[str, list[dict[str, Any]]] = {}
    for name, endpoint in endpoints.items():
        payload, reason = market_v5._request_json(
            "fmp",
            f"https://financialmodelingprep.com/stable/{endpoint}",
            params={
                "symbol": resolved,
                "period": period,
                "limit": 8,
                "apikey": key,
            },
        )
        rows = payload if isinstance(payload, list) else []
        payloads[name] = [row for row in rows if isinstance(row, dict)]
        if not rows and reason:
            LOGGER.debug("FMP %s unavailable: %s", name, reason)
    merged = _merge_period_rows(payloads["income"], payloads["balance"], payloads["cash"])
    frame = _normalize_rows(merged, source="fmp", period_type=period_type)
    return frame, {"resolved_symbol": resolved, "statements": {key: len(value) for key, value in payloads.items()}}


def _eodhd_statement_rows(section: Any, period_type: str) -> list[dict[str, Any]]:
    if not isinstance(section, dict):
        return []
    key = "yearly" if period_type == "Annual" else "quarterly"
    values = section.get(key)
    if isinstance(values, dict):
        rows = []
        for date, row in values.items():
            if isinstance(row, dict):
                rows.append({"date": date, **row})
        return rows
    if isinstance(values, list):
        return [row for row in values if isinstance(row, dict)]
    return []


def _eodhd_statements(symbol: str, period_type: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    key = market_v5._secret("EODHD_API_KEY")
    resolved = market_v5.resolve_eodhd_symbol(symbol)
    if not key or not resolved:
        return pd.DataFrame(), {"reason": "not_configured_or_unresolved"}
    payload, reason = market_v5._request_json(
        "eodhd",
        f"https://eodhd.com/api/fundamentals/{resolved}",
        params={"api_token": key, "fmt": "json"},
        timeout=18,
    )
    if not isinstance(payload, dict):
        return pd.DataFrame(), {"reason": reason or "invalid_payload", "resolved_symbol": resolved}
    financials = payload.get("Financials") if isinstance(payload.get("Financials"), dict) else {}
    income = _eodhd_statement_rows(financials.get("Income_Statement"), period_type)
    balance = _eodhd_statement_rows(financials.get("Balance_Sheet"), period_type)
    cash = _eodhd_statement_rows(financials.get("Cash_Flow"), period_type)
    general = payload.get("General") if isinstance(payload.get("General"), dict) else {}
    merged = _merge_period_rows(income, balance, cash)
    frame = _normalize_rows(
        merged,
        source="eodhd",
        period_type=period_type,
        currency=str(general.get("CurrencyCode") or ""),
    )
    return frame, {
        "resolved_symbol": resolved,
        "statements": {"income": len(income), "balance": len(balance), "cash": len(cash)},
    }


def _alpha_reports(payload: Any, period_type: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    key = "annualReports" if period_type == "Annual" else "quarterlyReports"
    values = payload.get(key)
    return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []


def _alpha_statements(symbol: str, period_type: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    key = market_v5._secret("ALPHAVANTAGE_API_KEY")
    resolved = market_v5.resolve_alpha_symbol(symbol)
    if not key or not resolved:
        return pd.DataFrame(), {"reason": "not_configured_or_unresolved"}
    payloads: dict[str, list[dict[str, Any]]] = {}
    for name, function in (
        ("income", "INCOME_STATEMENT"),
        ("balance", "BALANCE_SHEET"),
        ("cash", "CASH_FLOW"),
    ):
        payload, reason = market_v5._request_json(
            "alphavantage",
            "https://www.alphavantage.co/query",
            params={"function": function, "symbol": resolved, "apikey": key},
            timeout=18,
        )
        rows = _alpha_reports(payload, period_type)
        payloads[name] = rows
        if not rows and reason:
            LOGGER.debug("Alpha Vantage %s unavailable: %s", name, reason)
    merged = _merge_period_rows(payloads["income"], payloads["balance"], payloads["cash"])
    frame = _normalize_rows(merged, source="alphavantage", period_type=period_type)
    return frame, {"resolved_symbol": resolved, "statements": {key: len(value) for key, value in payloads.items()}}


_ADAPTERS: dict[str, Callable[[str, str], tuple[pd.DataFrame, dict[str, Any]]]] = {
    "fmp": _fmp_statements,
    "eodhd": _eodhd_statements,
    "alphavantage": _alpha_statements,
}


@lru_cache(maxsize=512)
def _fetch_cached(
    symbol: str, period_type: str, bucket: int
) -> tuple[str, str]:
    _ = bucket
    attempts: list[dict[str, Any]] = []
    for provider in configured_financial_order():
        secret_name = market_v5._SECRET_NAMES.get(provider, "")
        if not secret_name or not market_v5._secret(secret_name):
            attempts.append({"provider": provider, "ok": False, "reason": "not_configured"})
            continue
        started = time.perf_counter()
        try:
            frame, meta = _ADAPTERS[provider](symbol, period_type)
        except Exception as exc:
            LOGGER.exception("%s financial adapter failed", provider)
            frame, meta = pd.DataFrame(), {"reason": type(exc).__name__.lower()}
        quality = assess_summary_quality(frame)
        attempts.append(
            {
                "provider": provider,
                "ok": bool(quality["pass"]),
                "reason": "" if quality["pass"] else ";".join(quality["issues"]),
                "quality_score": quality["score"],
                "periods": quality["periods"],
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                **meta,
            }
        )
        if not quality["pass"]:
            continue
        records = frame.where(pd.notna(frame), None).to_dict(orient="records")
        lineage = {
            "source": provider,
            "period_type": period_type,
            "quality": quality,
            "provider_attempts": attempts,
            "fusion_version": "5.0",
        }
        return json.dumps(records, ensure_ascii=False, default=str), json.dumps(
            lineage, ensure_ascii=False, default=str
        )
    return "[]", json.dumps(
        {"source": "unavailable", "provider_attempts": attempts, "fusion_version": "5.0"},
        ensure_ascii=False,
    )


def fetch_financial_summary(
    symbol: str, period_type: str = "Annual"
) -> tuple[pd.DataFrame, dict[str, Any]]:
    normalized_period = "Quarterly" if str(period_type).strip().lower().startswith("q") else "Annual"
    records_json, lineage_json = _fetch_cached(
        str(symbol).strip().upper(), normalized_period, int(time.time() // 3600)
    )
    records = json.loads(records_json)
    lineage = json.loads(lineage_json)
    frame = pd.DataFrame(records)
    if not frame.empty:
        frame["date"] = pd.to_datetime(frame["date"], errors="coerce")
        frame = frame.dropna(subset=["date"]).sort_values("date", ascending=False).reset_index(drop=True)
        frame.attrs["financial_lineage"] = lineage
        frame.attrs["source"] = lineage.get("source")
    return frame, lineage


__all__ = [
    "assess_summary_quality",
    "configured_financial_order",
    "fetch_financial_summary",
]
