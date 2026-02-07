from osoli_logging import log_exception
# financial_analysis/metrics.py

from typing import Tuple, List, Dict, Any

import pandas as pd
import yfinance as yf

from market_data import get_ticker_symbol
from .store import get_stored_financials_df
from .utils import _safe_float, _safe_div
import time

# ==============================================================
# 🧠 Lightweight cache for Yahoo info (to reduce rate limits)
# ==============================================================
_YAHOO_INFO_CACHE: Dict[str, Any] = {}
_YAHOO_INFO_CACHE_TS: Dict[str, float] = {}
_YAHOO_INFO_TTL_SEC = 60 * 60 * 24  # 24 hours
_YAHOO_INFO_COOLDOWN_SEC = 20       # cooldown after failures/429-ish
_YAHOO_INFO_LAST_FAIL: Dict[str, float] = {}


# ==============================================================
# 📐 Fundamental Ratios (Piotroski + Graham + Advanced Pack)
# ==============================================================

def _fetch_yahoo_info(symbol: str) -> dict:
    """Fetch Yahoo `info` with caching + cooldown to reduce rate limits."""
    sym = str(symbol or "").strip()
    if not sym:
        return {}

    now = time.time()

    # Fresh cache
    ts = _YAHOO_INFO_CACHE_TS.get(sym, 0.0)
    if ts and (now - ts) < _YAHOO_INFO_TTL_SEC:
        cached = _YAHOO_INFO_CACHE.get(sym)
        if isinstance(cached, dict):
            return cached

    # Cooldown after failures
    last_fail = _YAHOO_INFO_LAST_FAIL.get(sym, 0.0)
    if last_fail and (now - last_fail) < _YAHOO_INFO_COOLDOWN_SEC:
        cached = _YAHOO_INFO_CACHE.get(sym)
        return cached if isinstance(cached, dict) else {}

    try:
        t = yf.Ticker(sym)
        info = getattr(t, "info", {}) or {}
        if not isinstance(info, dict):
            info = {}
        _YAHOO_INFO_CACHE[sym] = info
        _YAHOO_INFO_CACHE_TS[sym] = now
        return info
    except Exception:
        _YAHOO_INFO_LAST_FAIL[sym] = now
        cached = _YAHOO_INFO_CACHE.get(sym)
        return cached if isinstance(cached, dict) else {}


def _best_key(row: pd.Series, keys: List[str], default=0.0) -> float:
    for k in keys:
        if k in row.index:
            v = _safe_float(row.get(k, 0.0))
            if v != 0:
                return v
    return _safe_float(default)


def _compute_dupont(curr_row: pd.Series) -> dict:
    out = {
        "DuPont_Profit_Margin": 0.0,
        "DuPont_Asset_Turnover": 0.0,
        "DuPont_Equity_Multiplier": 0.0,
        "ROE": 0.0,
        "ROA": 0.0,
        "Asset_Turnover": 0.0,
    }
    try:
        rev = _safe_float(curr_row.get("revenue", 0))
        ni = _safe_float(curr_row.get("net_income", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))
        eq = _safe_float(curr_row.get("total_equity", 0))

        pm = _safe_div(ni, rev, 0.0)
        at = _safe_div(rev, assets, 0.0)
        em = _safe_div(assets, eq, 0.0)

        roe = pm * at * em if (pm and at and em) else _safe_div(ni, eq, 0.0)
        roa = _safe_div(ni, assets, 0.0)

        out["DuPont_Profit_Margin"] = float(pm)
        out["DuPont_Asset_Turnover"] = float(at)
        out["DuPont_Equity_Multiplier"] = float(em)
        out["ROE"] = float(roe)
        out["ROA"] = float(roa)
        out["Asset_Turnover"] = float(at)
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return out


def _compute_liquidity_leverage(curr_row: pd.Series, prev_row: pd.Series = None) -> dict:
    out = {
        "Current_Ratio": 0.0,
        "Working_Capital": 0.0,
        "Debt_to_Equity": 0.0,
        "Liabilities_to_Assets": 0.0,
        "LT_Debt_Trend": 0.0,
    }
    try:
        ca = _safe_float(curr_row.get("current_assets", 0))
        cl = _safe_float(curr_row.get("current_liabilities", 0))
        ltd = _safe_float(curr_row.get("long_term_debt", 0))
        eq = _safe_float(curr_row.get("total_equity", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))

        out["Current_Ratio"] = float(_safe_div(ca, cl, 0.0))
        out["Working_Capital"] = float(ca - cl)

        out["Debt_to_Equity"] = float(_safe_div(ltd, eq, 0.0))
        out["Liabilities_to_Assets"] = float(_safe_div(_safe_float(curr_row.get("total_liabilities", 0)), assets, 0.0))

        if prev_row is not None:
            ltd_p = _safe_float(prev_row.get("long_term_debt", 0))
            out["LT_Debt_Trend"] = float(ltd - ltd_p)
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return out


def _compute_efficiency(curr_row: pd.Series, prev_row: pd.Series = None) -> dict:
    out = {"Gross_Margin": 0.0, "Operating_Margin": 0.0, "Net_Margin": 0.0}
    try:
        rev = _safe_float(curr_row.get("revenue", 0))
        gp = _safe_float(curr_row.get("gross_profit", 0))
        op = _safe_float(curr_row.get("operating_income", 0))
        ni = _safe_float(curr_row.get("net_income", 0))

        out["Gross_Margin"] = float(_safe_div(gp, rev, 0.0))
        out["Operating_Margin"] = float(_safe_div(op, rev, 0.0))
        out["Net_Margin"] = float(_safe_div(ni, rev, 0.0))
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return out


def _compute_quality(curr_row: pd.Series, prev_row: pd.Series = None) -> dict:
    out = {
        "OCF_to_NetIncome": 0.0,
        "Accruals_Ratio": 0.0,
    }
    try:
        ni = _safe_float(curr_row.get("net_income", 0))
        ocf = _safe_float(curr_row.get("operating_cash_flow", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))

        out["OCF_to_NetIncome"] = float(_safe_div(ocf, ni, 0.0))
        out["Accruals_Ratio"] = float(_safe_div((ni - ocf), assets, 0.0))
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return out


def _growth_rate(curr: float, prev: float) -> float:
    if prev == 0:
        return 0.0
    return float((curr - prev) / abs(prev))


def compute_fundamental_metrics(symbol: str) -> Dict[str, Any]:
    metrics = {
        # core
        "Piotroski": 0,
        "Graham": 0,
        "Valuation": 0,
        "DuPont": {},
        "LiquidityLeverage": {},
        "Efficiency": {},
        "Quality": {},

        # additional
        "Revenue_Growth_YoY": 0.0,
        "NetIncome_Growth_YoY": 0.0,
        "Interest_Coverage": 0.0,
        "Interest_Coverage_Quality": "partial",

        # optional flags (for gates later)
        "_fund_flags": {},
    }

    symbol = get_ticker_symbol(symbol)

    df = get_stored_financials_df(symbol, "Annual")
    if df.empty:
        df = get_stored_financials_df(symbol, "Quarterly")
    if df.empty:
        return metrics

    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr

    info = _fetch_yahoo_info(symbol)

    try:
        # --------------------------
        # Piotroski (simple internal)
        # --------------------------
        score = 0

        net_income_c = _safe_float(curr.get("net_income", 0))
        ocf_c = _safe_float(curr.get("operating_cash_flow", 0))
        assets_c = _safe_float(curr.get("total_assets", 1)) or 1.0

        net_income_p = _safe_float(prev.get("net_income", 0))
        assets_p = _safe_float(prev.get("total_assets", 1)) or 1.0

        if net_income_c > 0:
            score += 1
        if ocf_c > 0:
            score += 1

        roa_c = net_income_c / assets_c
        roa_p = net_income_p / assets_p
        if roa_c > roa_p:
            score += 1

        if ocf_c > net_income_c:
            score += 1

        ltd_c = _safe_float(curr.get("long_term_debt", 0))
        ltd_p = _safe_float(prev.get("long_term_debt", 0))
        if ltd_c <= ltd_p:
            score += 1

        cr_c = _safe_div(_safe_float(curr.get("current_assets", 0)), _safe_float(curr.get("current_liabilities", 0)), 0.0)
        cr_p = _safe_div(_safe_float(prev.get("current_assets", 0)), _safe_float(prev.get("current_liabilities", 0)), 0.0)
        if cr_c >= cr_p:
            score += 1

        rev_c = _safe_float(curr.get("revenue", 0))
        rev_p = _safe_float(prev.get("revenue", 0))
        if rev_c > rev_p:
            score += 1

        gm_c = _safe_div(_safe_float(curr.get("gross_profit", 0)), rev_c, 0.0)
        gm_p = _safe_div(_safe_float(prev.get("gross_profit", 0)), rev_p, 0.0)
        if gm_c >= gm_p:
            score += 1

        # asset turnover proxy
        at_c = _safe_div(rev_c, assets_c, 0.0)
        at_p = _safe_div(rev_p, assets_p, 0.0)
        if at_c >= at_p:
            score += 1

        metrics["Piotroski"] = int(score)

        # --------------------------
        # Graham (basic checks)
        # --------------------------
        g = 0
        # defensive rules simplified
        if cr_c >= 1.5:
            g += 1
        if ltd_c <= assets_c * 0.5:
            g += 1
        if net_income_c > 0:
            g += 1
        if rev_c > 0:
            g += 1
        metrics["Graham"] = int(g)

        # --------------------------
        # Valuation (placeholder)
        # --------------------------
        mcap = _safe_float(info.get("marketCap", 0))
        pe = _safe_float(info.get("trailingPE", 0))
        pb = _safe_float(info.get("priceToBook", 0))
        v = 0
        if pe > 0 and pe < 20:
            v += 1
        if pb > 0 and pb < 3:
            v += 1
        if mcap > 0:
            v += 1
        metrics["Valuation"] = int(v)

        # --------------------------
        # Packs
        # --------------------------
        metrics["DuPont"] = _compute_dupont(curr)
        metrics["LiquidityLeverage"] = _compute_liquidity_leverage(curr, prev)
        metrics["Efficiency"] = _compute_efficiency(curr, prev)
        metrics["Quality"] = _compute_quality(curr, prev)

        # --------------------------
        # Growth
        # --------------------------
        metrics["Revenue_Growth_YoY"] = float(_growth_rate(rev_c, rev_p))
        metrics["NetIncome_Growth_YoY"] = float(_growth_rate(net_income_c, net_income_p))

        # --------------------------
        # Interest coverage (best effort)
        # --------------------------
        ebit = _safe_float(curr.get("operating_income", 0))
        interest = _safe_float(curr.get("interest_expense", 0))
        if interest != 0:
            metrics["Interest_Coverage"] = float(_safe_div(ebit, abs(interest), 0.0))
            metrics["Interest_Coverage_Quality"] = "ok"
        else:
            metrics["Interest_Coverage"] = 0.0
            metrics["Interest_Coverage_Quality"] = "partial"

    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")

    return metrics