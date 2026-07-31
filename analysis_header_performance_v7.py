"""Non-blocking analysis header quote backed by the shared data cache."""
from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable

import pandas as pd

from performance_runtime_v7 import (
    peek_cached_quote,
    record_phase,
    warm_quote_cache,
)
from sc_runtime_v9 import peek_latest_cached_history

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_INSTALLED_MODULES: set[int] = set()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _empty_quote() -> dict[str, Any]:
    return {
        "price": None,
        "change": None,
        "source": "تحديث بالخلفية",
        "fetched_at": "—",
        "is_stale": True,
        "refreshing": True,
    }


def _from_history(symbol: str) -> dict[str, Any]:
    try:
        frame = peek_latest_cached_history(
            symbol,
            interval="1d",
            allow_stale=True,
        )
        if (
            not isinstance(frame, pd.DataFrame)
            or frame.empty
            or "Close" not in frame
        ):
            return {}
        close = pd.to_numeric(frame["Close"], errors="coerce").dropna()
        if close.empty:
            return {}
        price = float(close.iloc[-1])
        previous = float(close.iloc[-2]) if len(close) > 1 else None
        change = (
            (price / previous - 1.0) * 100.0
            if previous is not None and previous > 0
            else None
        )
        attrs = dict(getattr(frame, "attrs", {}) or {})
        lineage = dict(attrs.get("data_lineage") or {})
        stale = bool(lineage.get("is_stale", True))
        return {
            "price": price,
            "change": change,
            "source": str(
                lineage.get("source") or attrs.get("source") or "history"
            ),
            "fetched_at": str(lineage.get("fetched_at") or "—"),
            "is_stale": stale,
            "refreshing": stale,
        }
    except Exception:
        LOGGER.debug("Cached analysis history lookup failed", exc_info=True)
        return {}


def _warm_safely(symbol: str) -> None:
    try:
        warm_quote_cache(symbol)
    except Exception:
        LOGGER.debug("Analysis quote background warm failed", exc_info=True)


def _install_optional_legacy_renderer(module: Any) -> None:
    """Patch the retired technical-tab renderer only when it still exists."""
    original_safe_render = getattr(module, "_safe_render", None)
    if not callable(original_safe_render):
        return

    def safe_render(
        title: str,
        module_name: str,
        attr_name: str,
        *args: Any,
    ) -> None:
        if module_name == "views.analysis.technical":
            try:
                target = __import__(module_name, fromlist=["*"])
                from chart_performance_v7 import render_chart_from_frame

                def render_chart(
                    symbol: str,
                    interval: str,
                    period: str,
                    frame: pd.DataFrame,
                ) -> None:
                    try:
                        render_chart_from_frame(
                            symbol,
                            frame,
                            period=period,
                            interval=interval,
                        )
                    except Exception:
                        LOGGER.exception("Cached technical chart failed")
                        if not frame.empty:
                            target.st.dataframe(
                                frame.tail(30),
                                use_container_width=True,
                            )
                        else:
                            target.st.warning("تعذر عرض الشارت")
                    target.st.caption(
                        "الاختراق أو الكسر لا يُعتمد إلا بعد إغلاق "
                        "الشمعة على الفاصل المحدد."
                    )

                target._render_chart = render_chart
            except Exception:
                LOGGER.debug("Technical chart reuse patch deferred", exc_info=True)
        original_safe_render(title, module_name, attr_name, *args)

    module._safe_render = safe_render


def _normalize_symbol(module: Any, symbol: str) -> str:
    for name in ("get_ticker_symbol", "normalize_symbol"):
        normalizer = getattr(module, name, None)
        if not callable(normalizer):
            continue
        try:
            value = normalizer(symbol)
        except Exception:
            LOGGER.debug("Analysis symbol normalizer failed: %s", name, exc_info=True)
            continue
        if value:
            return str(value)
    return str(symbol or "").strip().upper()


def _fallback_quote(
    original: Callable[[str], Any] | None,
    symbol: str,
) -> dict[str, Any]:
    if callable(original):
        try:
            value = original(symbol)
            if isinstance(value, dict):
                return value
        except Exception:
            LOGGER.exception("Original analysis quote provider failed")
    return _empty_quote()


def install_analysis_header_performance(module: Any) -> None:
    """Add cache acceleration without making the analysis page depend on it."""
    module_id = id(module)
    if module_id in _INSTALLED_MODULES:
        return
    with _INSTALL_LOCK:
        if module_id in _INSTALLED_MODULES:
            return

        original_snapshot = getattr(module, "_price_snapshot", None)
        original_snapshot = original_snapshot if callable(original_snapshot) else None

        def price_snapshot(symbol: str) -> dict[str, Any]:
            started = time.perf_counter()
            normalized = _normalize_symbol(module, symbol)
            try:
                payload = peek_cached_quote(normalized, allow_stale=True) or {}
                price = _number(payload.get("price"))
                previous = _number(
                    payload.get("prev_close", payload.get("previous_close"))
                )
                if price is not None:
                    change = (
                        (price / previous - 1.0) * 100.0
                        if previous is not None and previous > 0
                        else payload.get("change_pct")
                    )
                    result = {
                        "price": price,
                        "change": change,
                        "source": str(payload.get("source") or "cache"),
                        "fetched_at": str(payload.get("fetched_at") or "—"),
                        "is_stale": bool(payload.get("is_stale")),
                        "refreshing": bool(payload.get("is_stale")),
                    }
                else:
                    result = _from_history(normalized)
                    if not result:
                        result = _fallback_quote(original_snapshot, symbol)
            except Exception:
                LOGGER.exception("Accelerated analysis quote failed; using fallback")
                result = _fallback_quote(original_snapshot, symbol)

            if result.get("refreshing"):
                try:
                    threading.Thread(
                        target=_warm_safely,
                        args=(normalized,),
                        daemon=True,
                        name=f"osoli-quote-warm-{normalized[:20]}",
                    ).start()
                except Exception:
                    LOGGER.debug("Unable to start quote warm thread", exc_info=True)
            try:
                record_phase(
                    normalized,
                    "quote",
                    "header_quote_ms",
                    (time.perf_counter() - started) * 1000.0,
                )
            except Exception:
                LOGGER.debug("Unable to record analysis quote timing", exc_info=True)
            return result if isinstance(result, dict) else _empty_quote()

        module._price_snapshot = price_snapshot
        _install_optional_legacy_renderer(module)
        module._analysis_header_performance_v11_installed = True
        _INSTALLED_MODULES.add(module_id)


__all__ = ["install_analysis_header_performance"]
