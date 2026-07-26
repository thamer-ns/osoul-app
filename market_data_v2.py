"""Hardened market-data facade.

Keeps the existing providers as the primary implementation, fixes missing-value
semantics, and restores the Argaam fallback without changing the public API.
"""
from __future__ import annotations

import re
from typing import Any, Dict, Iterable

import pandas as pd

from market_data import (
    fetch_batch_data as _legacy_fetch_batch_data,
    get_chart_history as _legacy_get_chart_history,
    get_tasi_data,
    get_ticker_symbol,
)

try:
    import requests
    from bs4 import BeautifulSoup
except Exception:  # pragma: no cover
    requests = None
    BeautifulSoup = None


def _num(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or pd.isna(value):
            return float(default)
        return float(str(value).replace(",", "").replace("SAR", "").replace("ر.س", "").strip())
    except Exception:
        return float(default)


def _reasonable_price(value: Any) -> bool:
    price = _num(value)
    return 0.000001 < price < 10_000_000


def fetch_price_from_argaam(symbol: str) -> float:
    """Best-effort Saudi price fallback."""
    if requests is None or BeautifulSoup is None:
        return 0.0
    code = get_ticker_symbol(symbol).replace(".SR", "").replace("^", "")
    if not code.isdigit():
        return 0.0

    urls = (
        f"https://www.argaam.com/ar/company/stock/overview/{code}",
        f"https://www.argaam.com/ar/company/stock/quote/{code}",
        f"https://www.argaam.com/en/company/stock/overview/{code}",
    )
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept-Language": "ar-SA,ar;q=0.9,en;q=0.7",
    }
    for url in urls:
        try:
            response = requests.get(url, headers=headers, timeout=8)
            if response.status_code != 200 or not response.text:
                continue
            soup = BeautifulSoup(response.text, "html.parser")
            for attrs in (
                {"property": "product:price:amount"},
                {"property": "og:price:amount"},
                {"itemprop": "price"},
            ):
                tag = soup.find("meta", attrs=attrs)
                if tag and _reasonable_price(tag.get("content")):
                    return _num(tag.get("content"))
            for pattern in (
                r'"lastPrice"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)',
                r'"last_price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)',
                r'"price"\s*:\s*"?([0-9]+(?:\.[0-9]+)?)',
            ):
                match = re.search(pattern, response.text, re.IGNORECASE)
                if match and _reasonable_price(match.group(1)):
                    return _num(match.group(1))
        except Exception:
            continue
    return 0.0


def _aliases(raw: str, normalized: str) -> list[str]:
    values = [raw, raw.upper(), normalized, normalized.upper()]
    if normalized.endswith(".SR"):
        values.append(normalized[:-3])
    return list(dict.fromkeys(x for x in values if x))


def fetch_batch_data(symbols_list: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    symbols = [str(x).strip() for x in symbols_list if str(x).strip()]
    legacy = _legacy_fetch_batch_data(symbols) or {}
    output: Dict[str, Dict[str, Any]] = {}

    for raw in symbols:
        normalized = get_ticker_symbol(raw) or raw.upper()
        payload = (
            legacy.get(raw)
            or legacy.get(raw.upper())
            or legacy.get(normalized)
            or legacy.get(normalized.upper())
            or {}
        )
        payload = dict(payload) if isinstance(payload, dict) else {}
        price = _num(payload.get("price"), 0.0)
        source = str(payload.get("source") or "failed")

        if price <= 0:
            argaam_price = fetch_price_from_argaam(normalized)
            if argaam_price > 0:
                price = argaam_price
                source = "argaam"

        prev_raw = payload.get("prev_close", payload.get("previous_close"))
        prev_close = _num(prev_raw, 0.0)
        has_prev = prev_close > 0
        change_pct = ((price - prev_close) / prev_close * 100.0) if price > 0 and has_prev else None

        cleaned = {
            "symbol": normalized,
            "price": price if price > 0 else None,
            "prev_close": prev_close if has_prev else None,
            "previous_close": prev_close if has_prev else None,
            "change_pct": round(change_pct, 2) if change_pct is not None else None,
            "change_percent": round(change_pct, 2) if change_pct is not None else None,
            "year_high": _num(payload.get("year_high"), 0.0) or None,
            "year_low": _num(payload.get("year_low"), 0.0) or None,
            "source": source,
            "ok": price > 0,
            "warnings": [] if has_prev else ["الإغلاق السابق غير متاح؛ لم تُفترض نسبة تغير صفرية."],
        }
        for key in _aliases(raw, normalized):
            output[key] = dict(cleaned)
    return output


def get_chart_history(
    symbol: str,
    period: str | None = None,
    interval: str = "1d",
    years: int = 5,
) -> pd.DataFrame:
    frame = _legacy_get_chart_history(symbol, period=period, interval=interval, years=years)
    if frame is None or not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    frame = frame.copy()
    lineage = dict(frame.attrs.get("data_lineage") or {})
    if not lineage:
        lineage = {
            "symbol": get_ticker_symbol(symbol),
            "interval": interval,
            "source": frame.attrs.get("source", "unknown"),
            "rows": len(frame),
            "start": str(frame.index.min()) if not frame.empty else None,
            "end": str(frame.index.max()) if not frame.empty else None,
        }
    frame.attrs["data_lineage"] = lineage
    return frame


def get_data_lineage(frame: pd.DataFrame) -> Dict[str, Any]:
    if frame is None or not isinstance(frame, pd.DataFrame):
        return {}
    return dict(frame.attrs.get("data_lineage") or {})
