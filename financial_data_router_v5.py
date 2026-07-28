"""Runtime financial-data router for Osoli v5.

Local/manual records stay first.  Official remote providers are consulted only
when the local summary fails minimum analytical coverage.  The router patches
already-imported references used by quality checks and metrics so all financial
consumers see the same source and lineage.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from financial_providers_v5 import assess_summary_quality, fetch_financial_summary

LOGGER = logging.getLogger(__name__)
_INSTALLED = False


def _with_lineage(
    frame: pd.DataFrame,
    *,
    lineage: dict[str, Any],
    local_quality: dict[str, Any] | None = None,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        return pd.DataFrame()
    output = frame.copy()
    merged = dict(lineage or {})
    if local_quality is not None:
        merged["local_quality"] = local_quality
    output.attrs.update(dict(getattr(frame, "attrs", {}) or {}))
    output.attrs["financial_lineage"] = merged
    output.attrs["source"] = merged.get("source") or output.attrs.get("source")
    return output


def install_financial_data_router() -> None:
    global _INSTALLED
    if _INSTALLED:
        return

    import financial_analysis.store as store

    original_get = store.get_stored_financials_df

    def get_stored_financials_df(symbol: str, period_type: str = "Annual") -> pd.DataFrame:
        try:
            local = original_get(symbol, period_type)
            if not isinstance(local, pd.DataFrame):
                local = pd.DataFrame()
        except Exception:
            LOGGER.exception("Local financial statement read failed for %s", symbol)
            local = pd.DataFrame()
        local_quality = assess_summary_quality(local)
        if local_quality.get("pass"):
            return _with_lineage(
                local,
                lineage={
                    "source": "stored_database",
                    "period_type": period_type,
                    "quality": local_quality,
                    "fallback_used": False,
                    "fusion_version": "5.0",
                },
            )

        remote, remote_lineage = fetch_financial_summary(symbol, period_type)
        if isinstance(remote, pd.DataFrame) and not remote.empty:
            return _with_lineage(
                remote,
                lineage={
                    **remote_lineage,
                    "fallback_used": True,
                    "local_source_available": not local.empty,
                },
                local_quality=local_quality,
            )
        if not local.empty:
            return _with_lineage(
                local,
                lineage={
                    "source": "stored_database_partial",
                    "period_type": period_type,
                    "quality": local_quality,
                    "provider_attempts": list(remote_lineage.get("provider_attempts") or []),
                    "fallback_used": False,
                    "fusion_version": "5.0",
                },
            )
        empty = pd.DataFrame()
        empty.attrs["financial_lineage"] = {
            **remote_lineage,
            "local_quality": local_quality,
        }
        return empty

    store.get_stored_financials_df = get_stored_financials_df

    # Modules import this function directly, so patch their bound references too.
    try:
        import financial_analysis.metrics as metrics

        metrics.get_stored_financials_df = get_stored_financials_df
    except Exception:
        LOGGER.debug("Metrics binding patch deferred", exc_info=True)
    try:
        import financial_analysis.data_quality as data_quality

        data_quality.get_stored_financials_df = get_stored_financials_df
    except Exception:
        LOGGER.debug("Data-quality binding patch deferred", exc_info=True)
    try:
        import financial_analysis.ui as financial_ui

        if hasattr(financial_ui, "get_stored_financials_df"):
            financial_ui.get_stored_financials_df = get_stored_financials_df
    except Exception:
        LOGGER.debug("Financial UI binding patch deferred", exc_info=True)

    store._financial_fusion_v5_installed = True
    _INSTALLED = True


__all__ = ["install_financial_data_router"]
