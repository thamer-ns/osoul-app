"""Runtime fixes for market_data provider fallbacks and lineage."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

import streamlit as st

_INSTALLED = False


def install_market_data_hardening() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    import market_data as md

    original_batch = md.fetch_batch_data

    def fetch_price_from_argaam(symbol: str) -> float:
        code = str(md.get_ticker_symbol(symbol) or symbol or "").upper().replace(".SR", "").replace("^", "")
        if not code.isdigit():
            return 0.0
        urls = (
            f"https://www.argaam.com/ar/company/stock/overview/{code}",
            f"https://www.argaam.com/en/company/stock/overview/{code}",
            f"https://www.argaam.com/ar/company/stock/quote/{code}",
        )
        for url in urls:
            try:
                response = md._http_get(url, timeout=7, retries=1)
                if not response:
                    continue
                price = float(md._extract_argaam_price_from_html(response.text) or 0.0)
                if md._is_reasonable_price(price):
                    return price
            except Exception:
                continue
        return 0.0

    def fetch_argaam_snapshot(symbol: str) -> Dict[str, Any]:
        price = fetch_price_from_argaam(symbol)
        return {
            "symbol": str(symbol or ""),
            "price": float(price or 0.0),
            "prev_close": 0.0,
            "source": "argaam",
            "ok": bool(price > 0),
            "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        }

    @st.cache_data(ttl=120, show_spinner=False)
    def fetch_batch_data(symbols_list: list):
        data = original_batch(symbols_list) or {}
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        for raw_symbol in [str(x).strip().upper() for x in symbols_list or [] if str(x).strip()]:
            norm = md.get_ticker_symbol(raw_symbol) or raw_symbol
            payload = data.get(raw_symbol) or data.get(norm) or {}
            payload = dict(payload or {})

            price = float(payload.get("price") or 0.0)
            prev = float(payload.get("prev_close") or payload.get("previous_close") or 0.0)
            source = str(payload.get("source") or "failed")

            if price <= 0:
                argaam = fetch_argaam_snapshot(norm)
                if argaam.get("ok"):
                    price = float(argaam["price"])
                    prev = 0.0
                    source = "argaam"

            if source in {"google_finance", "tradingview", "investing", "argaam"} and price > 0 and abs(prev - price) < 1e-12:
                prev = 0.0

            change = ((price - prev) / prev * 100.0) if price > 0 and prev > 0 else None
            payload.update(
                {
                    "symbol": norm,
                    "price": price,
                    "prev_close": prev,
                    "previous_close": prev,
                    "change_pct": round(change, 2) if change is not None else None,
                    "change_percent": round(change, 2) if change is not None else None,
                    "change_available": change is not None,
                    "source": source,
                    "fetched_at": now,
                    "is_stale": price <= 0,
                }
            )
            for key in {raw_symbol, raw_symbol.upper(), norm, norm.upper()}:
                data[key] = dict(payload)
        return data

    md.fetch_price_from_argaam = fetch_price_from_argaam
    md.fetch_argaam_snapshot = fetch_argaam_snapshot
    md.fetch_batch_data = fetch_batch_data
    _INSTALLED = True
