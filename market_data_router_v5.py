"""Runtime router that upgrades ``market_data`` to provider fusion v5.

It is installed after the legacy hardening layer, captures those hardened
functions as the final fallback, then places official API providers in front of
Yahoo and HTML best-effort sources.  Existing call signatures and aliases stay
unchanged so charts, portfolio accounting and the AI engine migrate together.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from market_providers_v5 import fetch_history, fetch_quote, provider_status

LOGGER = logging.getLogger(__name__)
_INSTALLED = False


def _years_from_request(period: str | None, years: int | None, interval: str) -> int:
    if years:
        try:
            return max(1, min(25, int(years)))
        except (TypeError, ValueError, OverflowError):
            pass
    raw = str(period or "").strip().lower()
    match = re.fullmatch(r"(\d+)y", raw)
    if match:
        return max(1, min(25, int(match.group(1))))
    if raw == "max":
        return 20
    if raw.endswith("mo"):
        try:
            return max(1, min(5, (int(raw[:-2]) + 11) // 12))
        except (TypeError, ValueError):
            return 2
    normalized = str(interval or "1d").lower()
    return 15 if normalized in {"1wk", "1w", "1mo"} else 5


def _minimum_rows(interval: str) -> int:
    normalized = str(interval or "1d").strip().lower()
    if normalized in {"1mo", "month", "monthly"}:
        return 24
    if normalized in {"1wk", "1w", "week", "weekly"}:
        return 52
    if normalized in {"1d", "day", "daily"}:
        return 60
    return 80


def _merge_attempts(frame: pd.DataFrame, attempts: list[dict[str, Any]], *, fallback_source: str = "") -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    output = frame.copy()
    attrs = dict(getattr(frame, "attrs", {}) or {})
    lineage = dict(attrs.get("data_lineage") or {})
    existing = list(lineage.get("provider_attempts") or [])
    lineage["provider_attempts"] = attempts + existing
    lineage["provider_fusion_version"] = "5.0"
    lineage["fallback_used"] = bool(fallback_source)
    if fallback_source:
        lineage["source"] = fallback_source
    lineage.setdefault(
        "fetched_at", datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    )
    attrs["data_lineage"] = lineage
    attrs["source"] = lineage.get("source") or attrs.get("source") or fallback_source
    output.attrs.update(attrs)
    return output


def install_market_data_router() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    import market_data as md

    original_history = md.get_chart_history
    original_batch = md.fetch_batch_data
    original_sources = getattr(md, "get_analysis_sources", None)

    def get_chart_history(
        symbol: str,
        period: str | None = None,
        interval: str = "1d",
        years: int = 5,
    ) -> pd.DataFrame:
        years_needed = _years_from_request(period, years, interval)
        frame, attempts = fetch_history(
            symbol,
            interval=interval,
            years=years_needed,
            minimum_rows=_minimum_rows(interval),
        )
        if isinstance(frame, pd.DataFrame) and not frame.empty:
            return frame
        try:
            fallback = original_history(
                symbol,
                period=period,
                interval=interval,
                years=years_needed,
            )
        except TypeError:
            fallback = original_history(symbol, period=period, interval=interval)
        except Exception:
            LOGGER.exception("Legacy history fallback failed for %s", symbol)
            fallback = pd.DataFrame()
        source = ""
        if isinstance(fallback, pd.DataFrame) and not fallback.empty:
            attrs = getattr(fallback, "attrs", {}) or {}
            source = str((attrs.get("data_lineage") or {}).get("source") or attrs.get("source") or "legacy_fallback")
        return _merge_attempts(fallback, attempts, fallback_source=source)

    def _store_aliases(
        output: dict[str, dict[str, Any]],
        raw_symbol: str,
        normalized: str,
        payload: dict[str, Any],
    ) -> None:
        keys = {raw_symbol, raw_symbol.upper(), normalized, normalized.upper()}
        try:
            keys.update(md._symbol_variants(normalized))
        except Exception:
            LOGGER.debug("Symbol alias expansion failed", exc_info=True)
        for key in keys:
            clean = str(key or "").strip().upper()
            if clean:
                output[clean] = dict(payload)

    def fetch_batch_data(symbols_list: list) -> dict[str, dict[str, Any]]:
        requested = [str(item).strip().upper() for item in symbols_list or [] if str(item).strip()]
        output: dict[str, dict[str, Any]] = {}
        failed: list[str] = []
        failed_attempts: dict[str, list[dict[str, Any]]] = {}

        for raw_symbol in requested:
            normalized = md.get_ticker_symbol(raw_symbol) or raw_symbol
            payload, attempts = fetch_quote(normalized)
            if payload:
                payload["symbol"] = normalized
                _store_aliases(output, raw_symbol, normalized, payload)
            else:
                failed.append(raw_symbol)
                failed_attempts[raw_symbol] = attempts

        legacy = original_batch(failed) if failed else {}
        now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        for raw_symbol in failed:
            normalized = md.get_ticker_symbol(raw_symbol) or raw_symbol
            payload = dict(
                legacy.get(raw_symbol)
                or legacy.get(raw_symbol.upper())
                or legacy.get(normalized)
                or {}
            )
            payload.setdefault("symbol", normalized)
            payload.setdefault("price", 0.0)
            payload.setdefault("prev_close", payload.get("previous_close") or 0.0)
            payload.setdefault("previous_close", payload.get("prev_close") or 0.0)
            payload.setdefault("change_pct", payload.get("change_percent"))
            payload.setdefault("change_percent", payload.get("change_pct"))
            payload.setdefault("change_available", payload.get("change_pct") is not None)
            payload.setdefault("source", "failed")
            payload.setdefault("fetched_at", now)
            payload.setdefault("is_stale", not bool(payload.get("price")))
            payload["provider_attempts"] = failed_attempts.get(raw_symbol, []) + list(
                payload.get("provider_attempts") or []
            )
            payload["provider_fusion_version"] = "5.0"
            _store_aliases(output, raw_symbol, normalized, payload)
        return output

    def get_tasi_history(period: str | None = None, interval: str = "1d") -> pd.DataFrame:
        return get_chart_history("TASI", period=period, interval=interval, years=15)

    def get_analysis_sources(symbol: str) -> dict[str, Any]:
        base: dict[str, Any] = {}
        if callable(original_sources):
            try:
                value = original_sources(symbol)
                base = dict(value) if isinstance(value, dict) else {}
            except Exception:
                LOGGER.debug("Legacy source diagnostics failed", exc_info=True)
        quote, attempts = fetch_quote(symbol)
        history, history_attempts = fetch_history(
            symbol, interval="1d", years=2, minimum_rows=60
        )
        base.setdefault("symbol", md.get_ticker_symbol(symbol))
        base["provider_fusion"] = {
            "version": "5.0",
            "status": provider_status(),
            "quote": quote,
            "quote_attempts": attempts,
            "history_source": str(
                ((getattr(history, "attrs", {}) or {}).get("data_lineage") or {}).get("source")
                or ""
            ),
            "history_rows": int(len(history)) if isinstance(history, pd.DataFrame) else 0,
            "history_attempts": history_attempts,
        }
        return base

    md.get_chart_history = get_chart_history
    md.fetch_batch_data = fetch_batch_data
    md.get_tasi_history = get_tasi_history
    md.get_analysis_sources = get_analysis_sources
    md.provider_status_v5 = provider_status
    md._provider_fusion_v5_installed = True
    _INSTALLED = True


__all__ = ["install_market_data_router"]
