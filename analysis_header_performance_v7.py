"""Non-blocking analysis header quote backed by the shared data cache."""
from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

import pandas as pd

from performance_runtime_v7 import (
    peek_cached_history,
    peek_cached_quote,
    record_phase,
    warm_quote_cache,
)

LOGGER = logging.getLogger(__name__)
_INSTALL_LOCK = threading.RLock()
_INSTALLED_MODULES: set[int] = set()


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if number > 0 else None


def _from_history(symbol: str) -> dict[str, Any]:
    frame = peek_cached_history(
        symbol,
        period="5d",
        interval="1d",
        years=5,
        allow_stale=True,
    )
    if not isinstance(frame, pd.DataFrame) or frame.empty or "Close" not in frame:
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
    return {
        "price": price,
        "change": change,
        "source": str(lineage.get("source") or attrs.get("source") or "history"),
        "fetched_at": str(lineage.get("fetched_at") or "—"),
        "is_stale": True,
        "refreshing": True,
    }


def install_analysis_header_performance(module: Any) -> None:
    """Replace blocking header data and pass the loaded frame to the chart."""
    module_id = id(module)
    if module_id in _INSTALLED_MODULES:
        return
    with _INSTALL_LOCK:
        if module_id in _INSTALLED_MODULES:
            return

        def price_snapshot(symbol: str) -> dict[str, Any]:
            started = datetime.now(timezone.utc)
            normalized = (
                module.get_ticker_symbol(symbol)
                or module.normalize_symbol(symbol)
                or str(symbol)
            )
            payload = peek_cached_quote(normalized, allow_stale=True)
            price = _number(payload.get("price")) if payload else None
            previous = (
                _number(payload.get("prev_close", payload.get("previous_close")))
                if payload
                else None
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
                result = _from_history(normalized) or {
                    "price": None,
                    "change": None,
                    "source": "تحديث بالخلفية",
                    "fetched_at": "—",
                    "is_stale": True,
                    "refreshing": True,
                }

            if result.get("refreshing"):
                threading.Thread(
                    target=warm_quote_cache,
                    args=(normalized,),
                    daemon=True,
                    name=f"osoli-quote-warm-{normalized[:20]}",
                ).start()
            elapsed = (
                datetime.now(timezone.utc) - started
            ).total_seconds() * 1000.0
            record_phase(normalized, "quote", "header_quote_ms", elapsed)
            return result

        module._price_snapshot = price_snapshot

        original_safe_render = module._safe_render

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
                    LOGGER.debug(
                        "Technical chart reuse patch deferred",
                        exc_info=True,
                    )
            original_safe_render(title, module_name, attr_name, *args)

        module._safe_render = safe_render
        module._analysis_header_performance_v7_installed = True
        _INSTALLED_MODULES.add(module_id)


__all__ = ["install_analysis_header_performance"]
