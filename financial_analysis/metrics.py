# financial_analysis/metrics.py

from typing import Tuple, List, Dict, Any

import pandas as pd
import yfinance as yf

from market_data import get_ticker_symbol
from .store import get_stored_financials_df
from .utils import _safe_float, _safe_div, _safe_float_none, _safe_div_none, _is_missing


# ==============================================================
# 📐 Fundamental Ratios (Piotroski + Graham + Advanced Pack)
# ==============================================================

def _fetch_yahoo_info(symbol: str) -> dict:
    try:
        t = yf.Ticker(symbol)
        info = getattr(t, "info", {}) or {}
        if not isinstance(info, dict):
            return {}
        return info
    except Exception:
        return {}


def _best_key(row: pd.Series, keys: List[str], default=0.0):
    for k in keys:
        if k in row.index:
            v = _safe_float_none(row.get(k, None))
            if v not in (None, 0):
                return v
    return _safe_float_none(default) if default is None else _safe_float(default)


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
    except Exception:
        pass
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
        liab = _safe_float(curr_row.get("total_liabilities", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))
        eq = _safe_float(curr_row.get("total_equity", 0))

        wc = ca - cl
        cr = _safe_div(ca, cl, 0.0)
        dte = _safe_div(ltd, eq, 0.0) if eq > 0 else _safe_div(liab, assets, 0.0)
        lta = _safe_div(liab, assets, 0.0)

        out["Working_Capital"] = float(wc)
        out["Current_Ratio"] = float(cr)
        out["Debt_to_Equity"] = float(dte)
        out["Liabilities_to_Assets"] = float(lta)

        if prev_row is not None:
            ltd_p = _safe_float(prev_row.get("long_term_debt", 0))
            if ltd_p != 0:
                out["LT_Debt_Trend"] = float((ltd - ltd_p) / abs(ltd_p))
    except Exception:
        pass
    return out


def _compute_earnings_quality(curr_row: pd.Series) -> dict:
    out = {
        "OCF_to_NetIncome": 0.0,
        "Accruals_to_Assets": 0.0,
        "OCF_Margin": 0.0,
    }
    try:
        ni = _safe_float(curr_row.get("net_income", 0))
        ocf = _safe_float(curr_row.get("operating_cash_flow", 0))
        assets = _safe_float(curr_row.get("total_assets", 0))
        rev = _safe_float(curr_row.get("revenue", 0))

        out["OCF_to_NetIncome"] = float(_safe_div(ocf, ni, 0.0)) if ni != 0 else (1.0 if ocf > 0 else 0.0)
        out["Accruals_to_Assets"] = float(_safe_div((ni - ocf), assets, 0.0))
        out["OCF_Margin"] = float(_safe_div(ocf, rev, 0.0))
    except Exception:
        pass
    return out


def _compute_efficiency_pack(curr_row: pd.Series) -> dict:
    """
    Best-effort margins:
    - Gross / Operating / Net margin
    Depends on availability in stored financials.
    """
    out = {
        "Gross_Margin": 0.0,
        "Operating_Margin": 0.0,
        "Net_Margin": 0.0,
    }
    try:
        rev = _safe_float(curr_row.get("revenue", 0))
        if rev <= 0:
            return out

        gp = _best_key(curr_row, ["gross_profit", "grossProfit"], default=0.0)
        op_inc = _best_key(curr_row, ["operating_income", "operatingIncome", "ebit"], default=0.0)
        ni = _safe_float(curr_row.get("net_income", 0))

        out["Gross_Margin"] = float(_safe_div(gp, rev, 0.0))
        out["Operating_Margin"] = float(_safe_div(op_inc, rev, 0.0))
        out["Net_Margin"] = float(_safe_div(ni, rev, 0.0))
    except Exception:
        pass
    return out


def _compute_cashflow_pack(curr_row: pd.Series) -> dict:
    """
    Best-effort FCF:
    - FCF = OCF - Capex (if capex exists)
    """
    out = {
        "Free_Cash_Flow": 0.0,
        "FCF_Margin": 0.0,
        "FCF_to_NetIncome": 0.0,
    }
    try:
        ocf = _safe_float(curr_row.get("operating_cash_flow", 0))
        capex = _best_key(curr_row, ["capex", "capital_expenditure", "capitalExpenditures"], default=0.0)
        rev = _safe_float(curr_row.get("revenue", 0))
        ni = _safe_float(curr_row.get("net_income", 0))

        # capex is usually negative in some sources; treat as cash outflow magnitude
        capex_out = abs(_safe_float(capex))
        fcf = ocf - capex_out

        out["Free_Cash_Flow"] = float(fcf)
        out["FCF_Margin"] = float(_safe_div(fcf, rev, 0.0)) if rev > 0 else 0.0
        out["FCF_to_NetIncome"] = float(_safe_div(fcf, ni, 0.0)) if ni != 0 else (1.0 if fcf > 0 else 0.0)
    except Exception:
        pass
    return out


def _compute_growth_pack(curr_row: pd.Series, prev_row: pd.Series) -> dict:
    out = {
        "Revenue_Growth_YoY": 0.0,
        "NetIncome_Growth_YoY": 0.0,
    }
    try:
        rev_c = _safe_float(curr_row.get("revenue", 0))
        rev_p = _safe_float(prev_row.get("revenue", 0))
        ni_c = _safe_float(curr_row.get("net_income", 0))
        ni_p = _safe_float(prev_row.get("net_income", 0))

        if rev_p != 0:
            out["Revenue_Growth_YoY"] = float((rev_c - rev_p) / abs(rev_p))
        if ni_p != 0:
            out["NetIncome_Growth_YoY"] = float((ni_c - ni_p) / abs(ni_p))
    except Exception:
        pass
    return out


def _compute_interest_coverage_best_effort(curr_row: pd.Series, yahoo_info: dict) -> dict:
    """
    Best-effort:
    - Interest coverage = EBIT / Interest expense
    Interest expense often missing; fallback to Yahoo if possible (rare).
    """
    out = {"Interest_Coverage": 0.0, "Interest_Coverage_Quality": "partial"}
    try:
        ebit = _best_key(curr_row, ["ebit", "operating_income", "operatingIncome"], default=0.0)
        ie = _best_key(curr_row, ["interest_expense", "interestExpense"], default=0.0)

        if ie == 0:
            # very best-effort: try Yahoo
            ie = _safe_float(yahoo_info.get("interestExpense"))
        if ie != 0:
            out["Interest_Coverage"] = float(_safe_div(ebit, abs(ie), 0.0))
            out["Interest_Coverage_Quality"] = "full"
    except Exception:
        pass
    return out


def _compute_altman_z_best_effort(symbol: str, curr_row: pd.Series, yahoo_info: dict) -> dict:
    out = {
        "Altman_Z": 0.0,
        "Altman_Z_Quality": "partial",
    }
    try:
        ta = _safe_float(curr_row.get("total_assets", 0))
        if ta <= 0:
            return out

        ca = _safe_float(curr_row.get("current_assets", 0))
        cl = _safe_float(curr_row.get("current_liabilities", 0))
        wc = ca - cl

        tl = _safe_float(curr_row.get("total_liabilities", 0))
        sales = _safe_float(curr_row.get("revenue", 0))

        ebit = 0.0
        retained = 0.0  # optional if not available

        ebitda = _safe_float(yahoo_info.get("ebitda"))
        if ebitda > 0:
            ebit = 0.7 * ebitda

        mve = _safe_float(yahoo_info.get("marketCap"))

        z = 0.0
        z += 1.2 * _safe_div(wc, ta, 0.0)
        z += 1.4 * _safe_div(retained, ta, 0.0)
        z += 3.3 * _safe_div(ebit, ta, 0.0)
        z += 0.6 * _safe_div(mve, tl, 0.0) if tl > 0 else 0.0
        z += 1.0 * _safe_div(sales, ta, 0.0)

        out["Altman_Z"] = float(z)
        out["Altman_Z_Quality"] = "full" if (ebit > 0 and mve > 0 and sales > 0 and tl > 0) else "partial"
    except Exception:
        pass
    return out


def _compute_sgr(roe: float, yahoo_info: dict) -> dict:
    out = {"SGR": 0.0, "Payout_Ratio": 0.0, "Retention_Ratio": 0.0, "SGR_Estimated": 0}
    try:
        payout = _safe_float(yahoo_info.get("payoutRatio"))
        if payout <= 0 or payout >= 1:
            payout = 0.30
            out["SGR_Estimated"] = 1

        retention = max(0.0, min(1.0, 1.0 - payout))
        out["Payout_Ratio"] = float(payout)
        out["Retention_Ratio"] = float(retention)
        out["SGR"] = float(_safe_float(roe) * retention)
    except Exception:
        pass
    return out


def _compute_valuation_pack(yahoo_info: dict) -> dict:
    out = {
        "PE_Trailing": 0.0,
        "PE_Forward": 0.0,
        "PEG": 0.0,
        "PB": 0.0,
        "MarketCap": 0.0,
        "EV": 0.0,
        "EV_to_EBITDA": 0.0,
        "Dividend_Yield": 0.0,
    }
    try:
        out["PE_Trailing"] = float(_safe_float(yahoo_info.get("trailingPE")))
        out["PE_Forward"] = float(_safe_float(yahoo_info.get("forwardPE")))
        out["PEG"] = float(_safe_float(yahoo_info.get("pegRatio")))
        out["PB"] = float(_safe_float(yahoo_info.get("priceToBook")))
        out["MarketCap"] = float(_safe_float(yahoo_info.get("marketCap")))
        out["EV"] = float(_safe_float(yahoo_info.get("enterpriseValue")))
        out["EV_to_EBITDA"] = float(_safe_float(yahoo_info.get("enterpriseToEbitda")))
        out["Dividend_Yield"] = float(_safe_float(yahoo_info.get("dividendYield")))
    except Exception:
        pass
    return out


def _build_fund_flags(metrics: dict) -> Dict[str, int]:
    """
    ✅ Flags جاهزة للـ gates لاحقًا
    """
    flags = {
        "fund_neg_ocf": 0,
        "fund_low_liquidity": 0,
        "fund_high_leverage": 0,
        "fund_altman_low": 0,
        "fund_strong_quality": 0,
        "fund_overvalued": 0,
        "fund_undervalued": 0,
    }
    try:
        ocf = _safe_float(metrics.get("operating_cash_flow", 0.0))
        # note: operating_cash_flow might not exist here; we infer from ratios
        ocf_margin = _safe_float(metrics.get("OCF_Margin", 0.0))
        if ocf_margin < 0:
            flags["fund_neg_ocf"] = 1

        cr = _safe_float(metrics.get("Current_Ratio", 0.0))
        if 0 < cr < 0.9:
            flags["fund_low_liquidity"] = 1

        lta = _safe_float(metrics.get("Liabilities_to_Assets", 0.0))
        if lta > 0.75:
            flags["fund_high_leverage"] = 1

        altz = _safe_float(metrics.get("Altman_Z", 0.0))
        if altz > 0 and altz < 1.8:
            flags["fund_altman_low"] = 1

        piot = int(metrics.get("Piotroski_Score", 0) or 0)
        ocf_ni = _safe_float(metrics.get("OCF_to_NetIncome", 0.0))
        if piot >= 7 and ocf_ni >= 1.0 and altz >= 3.0:
            flags["fund_strong_quality"] = 1

        pe = _safe_float(metrics.get("PE_Trailing", 0.0))
        peg = _safe_float(metrics.get("PEG", 0.0))
        if (pe >= 35) or (peg > 2.5):
            flags["fund_overvalued"] = 1
        if (peg > 0 and peg <= 1.2) and (pe > 0 and pe <= 16):
            flags["fund_undervalued"] = 1
    except Exception:
        pass
    return {k: int(v) for k, v in flags.items()}


def _score_fundamentals(metrics: dict) -> Tuple[int, str, List[str]]:
    score = 0
    opinions: List[str] = []

    try:
        piot = int(metrics.get("Piotroski_Score", 0) or 0)
        roe = _safe_float(metrics.get("ROE", 0))
        roa = _safe_float(metrics.get("ROA", 0))
        cr = _safe_float(metrics.get("Current_Ratio", 0))
        lta = _safe_float(metrics.get("Liabilities_to_Assets", 0))
        ocf_ni = _safe_float(metrics.get("OCF_to_NetIncome", 0))
        altz = _safe_float(metrics.get("Altman_Z", 0))
        altq = str(metrics.get("Altman_Z_Quality", "partial"))

        pe = _safe_float(metrics.get("PE_Trailing", 0))
        peg = _safe_float(metrics.get("PEG", 0))

        rev_g = _safe_float(metrics.get("Revenue_Growth_YoY", 0))
        ni_g = _safe_float(metrics.get("NetIncome_Growth_YoY", 0))
        fcf_m = _safe_float(metrics.get("FCF_Margin", 0))

        if piot >= 7:
            score += 3
            opinions.append("💎 Piotroski مرتفع (جودة مالية قوية)")
        elif piot <= 3:
            score -= 2
            opinions.append("⚠️ Piotroski منخفض (مخاطر مالية)")

        if roe >= 0.12:
            score += 2
            opinions.append("✅ ROE قوي (>= 12%)")
        elif roe <= 0.03 and roe > 0:
            score -= 1
            opinions.append("⚠️ ROE ضعيف")

        if roa >= 0.05:
            score += 1

        if cr >= 1.2:
            score += 1
            opinions.append("✅ السيولة جيدة (Current Ratio مناسب)")
        elif cr > 0 and cr < 0.9:
            score -= 1
            opinions.append("⚠️ السيولة ضعيفة (Current Ratio منخفض)")

        if lta > 0.75:
            score -= 1
            opinions.append("⚠️ التزامات مرتفعة مقارنة بالأصول")
        elif 0 < lta <= 0.55:
            score += 1

        if ocf_ni >= 1.0:
            score += 1
            opinions.append("✅ جودة أرباح جيدة (OCF ≥ Net Income)")
        elif 0 < ocf_ni < 0.6:
            score -= 1
            opinions.append("⚠️ جودة أرباح أقل (OCF أقل من صافي الربح)")

        if fcf_m > 0.06:
            score += 1
            opinions.append("✅ تدفق حر جيد (FCF Margin جيد)")
        elif fcf_m < 0:
            score -= 1
            opinions.append("⚠️ تدفق حر سلبي (FCF سلبي)")

        if altz > 0:
            if altz >= 3.0:
                score += 2
                opinions.append("✅ Altman Z قوي (مخاطر إفلاس منخفضة)")
            elif altz < 1.8:
                score -= 2
                opinions.append("⛔ Altman Z منخفض (مخاطر أعلى)")
            if altq != "full":
                opinions.append("ℹ️ Altman Z محسوب بشكل جزئي حسب المتوفر")

        # Growth (best-effort)
        if rev_g > 0.10:
            score += 1
            opinions.append("📈 نمو إيرادات جيد (YoY)")
        if ni_g > 0.10:
            score += 1
            opinions.append("📈 نمو أرباح جيد (YoY)")
        if rev_g < -0.10 and ni_g < -0.10:
            score -= 1
            opinions.append("📉 تراجع نمو ملحوظ (YoY)")

        if peg > 0 and peg <= 1.2:
            score += 1
            opinions.append("✅ PEG جيد (تقييم معقول مقابل النمو)")
        elif peg > 2.5:
            score -= 1
            opinions.append("⚠️ PEG مرتفع (تقييم مكلف)")

        if pe > 0 and pe <= 14:
            score += 1
        elif pe >= 35:
            score -= 1

    except Exception:
        pass

    score = int(max(0, min(10, score)))

    if score >= 8:
        rating = "قوي"
    elif score >= 6:
        rating = "جيد"
    elif score >= 4:
        rating = "متوسط"
    else:
        rating = "ضعيف"

    return score, rating, opinions


def get_advanced_fundamental_ratios(symbol):
    metrics: Dict[str, Any] = {
        "Fair_Value_Graham": 0.0,
        "Piotroski_Score": 0,
        "Financial_Health": "غير متوفر",
        "Score": 0,
        "Rating": "N/A",
        "Opinions": "",
        "ROE": 0.0,
        "ROA": 0.0,
        "DuPont_Profit_Margin": 0.0,
        "DuPont_Asset_Turnover": 0.0,
        "DuPont_Equity_Multiplier": 0.0,
        "Current_Ratio": 0.0,
        "Working_Capital": 0.0,
        "Debt_to_Equity": 0.0,
        "Liabilities_to_Assets": 0.0,
        "LT_Debt_Trend": 0.0,
        "OCF_to_NetIncome": 0.0,
        "Accruals_to_Assets": 0.0,
        "OCF_Margin": 0.0,
        "Altman_Z": 0.0,
        "Altman_Z_Quality": "partial",
        "SGR": 0.0,
        "Payout_Ratio": 0.0,
        "Retention_Ratio": 0.0,
        "SGR_Estimated": 0,
        "PE_Trailing": 0.0,
        "PE_Forward": 0.0,
        "PEG": 0.0,
        "PB": 0.0,
        "MarketCap": 0.0,
        "EV": 0.0,
        "EV_to_EBITDA": 0.0,
        "Dividend_Yield": 0.0,

        # ✅ New additions (safe)
        "Gross_Margin": 0.0,
        "Operating_Margin": 0.0,
        "Net_Margin": 0.0,
        "Free_Cash_Flow": 0.0,
        "FCF_Margin": 0.0,
        "FCF_to_NetIncome": 0.0,
        "Revenue_Growth_YoY": 0.0,
        "NetIncome_Growth_YoY": 0.0,
        "Interest_Coverage": 0.0,
        "Interest_Coverage_Quality": "partial",

        # optional flags (for gates later)
        "_fund_flags": {},
    }

    symbol = get_ticker_symbol(symbol)

    # Prefer Annual. Fallback to Quarterly but mark confidence lower (no mixing silently).
    period_used = "Annual"
    df = get_stored_financials_df(symbol, "Annual")
    if df.empty:
        df = get_stored_financials_df(symbol, "Quarterly")
        period_used = "Quarterly"
    if df.empty:
        return metrics

    curr = df.iloc[0]
    prev = df.iloc[1] if len(df) > 1 else curr

    # --------------------------
    # Data Quality / Completeness flags for UI + AI calibration
    # --------------------------
    essential = ["revenue", "net_income", "equity", "operating_cash_flow"]
    missing = []
    for k in essential:
        try:
            if k not in curr.index or curr.get(k) is None:
                missing.append(k)
        except Exception:
            missing.append(k)

    dq_score = 100
    if period_used == "Quarterly":
        dq_score -= 10
    dq_score -= min(40, 10 * len(missing))
    dq_score = int(max(0, min(100, dq_score)))

    metrics["Data_Period_Used"] = period_used
    metrics["Data_Confidence"] = dq_score
    metrics["Data_Issues"] = missing
    metrics.setdefault("_fund_flags", {})
    for k in missing:
        metrics["_fund_flags"][f"missing_{k}"] = 1

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
        if ltd_c < ltd_p:
            score += 1

        ca_c = _safe_float(curr.get("current_assets", 0))
        cl_c = _safe_float(curr.get("current_liabilities", 0))
        ca_p = _safe_float(prev.get("current_assets", 0))
        cl_p = _safe_float(prev.get("current_liabilities", 0))

        cr_c = ca_c / (cl_c or 1.0)
        cr_p = ca_p / (cl_p or 1.0)
        if cr_c > cr_p:
            score += 1

        eq_c = _safe_float(curr.get("total_equity", 0))
        eq_p = _safe_float(prev.get("total_equity", 0))
        if eq_c > eq_p and eq_c > 0:
            score += 1

        piotroski = int(min(max(score + 2, 0), 9))
        metrics["Piotroski_Score"] = piotroski
        metrics["Score"] = piotroski

        # --------------------------
        # Packs
        # --------------------------
        dup = _compute_dupont(curr)
        liq = _compute_liquidity_leverage(curr, prev)
        eqy = _compute_earnings_quality(curr)
        eff = _compute_efficiency_pack(curr)
        cfp = _compute_cashflow_pack(curr)
        grp = _compute_growth_pack(curr, prev)

        metrics.update(dup)
        metrics.update(liq)
        metrics.update(eqy)
        metrics.update(eff)
        metrics.update(cfp)
        metrics.update(grp)

        metrics.update(_compute_valuation_pack(info))

        # Graham Fair value
        try:
            eps = _safe_float(info.get("trailingEps"))
            bvps = _safe_float(info.get("bookValue"))
            if eps > 0 and bvps > 0:
                metrics["Fair_Value_Graham"] = float((22.5 * eps * bvps) ** 0.5)
        except Exception:
            pass

        metrics.update(_compute_altman_z_best_effort(symbol, curr, info))
        metrics.update(_compute_interest_coverage_best_effort(curr, info))
        metrics.update(_compute_sgr(metrics.get("ROE", 0.0), info))

        fscore10, rating, adv_ops = _score_fundamentals(metrics)

        # Health label
        if metrics["Piotroski_Score"] >= 7:
            metrics["Financial_Health"] = "جيد"
        elif metrics["Piotroski_Score"] <= 3:
            metrics["Financial_Health"] = "هش"
        else:
            metrics["Financial_Health"] = "متوسط"

        # Additional opinions
        if _safe_float(metrics.get("OCF_Margin", 0)) < 0:
            adv_ops.append("⚠️ التدفق النقدي التشغيلي سالب")

        if int(metrics.get("SGR_Estimated", 0)) == 1:
            adv_ops.append("ℹ️ SGR محسوب بافتراض payoutRatio (تقديري)")

        if _safe_float(metrics.get("PE_Trailing", 0)) == 0 and _safe_float(metrics.get("PEG", 0)) == 0:
            adv_ops.append("ℹ️ بيانات التقييم (PE/PEG) غير متوفرة من Yahoo")

        # Save rating/score/opinions
        metrics["Rating"] = rating
        metrics["Score"] = int(max(fscore10, int(metrics.get("Piotroski_Score", 0) or 0)))
        metrics["Opinions"] = " | ".join([str(x) for x in adv_ops if str(x).strip()])[:1200]

        # ✅ Fund flags for AI gates later
        metrics["_fund_flags"] = _build_fund_flags(metrics)

    except Exception:
        pass

    return metrics


def get_fundamental_ratios(symbol):
    return get_advanced_fundamental_ratios(symbol)



# ==============================================================
# ✅ OVERRIDE: missing -> None (عدم تحويل القيم الناقصة إلى صفر)
# الهدف: منع نسب مضللة (ROE/Margins/FCF...) عند غياب بيانات أساسية.
# هذه الدوال تُعيد None بدل 0.0 عندما تكون البيانات ناقصة.
# ==============================================================
def _v(x):
    return _safe_float_none(x)

def _d(a, b):
    return _safe_div_none(a, b)

def _compute_dupont(curr_row: pd.Series) -> dict:
    out = {
        "DuPont_Profit_Margin": None,
        "DuPont_Asset_Turnover": None,
        "DuPont_Equity_Multiplier": None,
        "ROE": None,
        "ROA": None,
        "Asset_Turnover": None,
    }
    try:
        rev = _v(curr_row.get("revenue"))
        ni = _v(curr_row.get("net_income"))
        assets = _v(curr_row.get("total_assets"))
        eq = _v(curr_row.get("total_equity"))

        pm = _d(ni, rev)
        at = _d(rev, assets)
        em = _d(assets, eq)

        roe = (pm * at * em) if (pm is not None and at is not None and em is not None) else _d(ni, eq)
        roa = _d(ni, assets)

        out["DuPont_Profit_Margin"] = pm
        out["DuPont_Asset_Turnover"] = at
        out["DuPont_Equity_Multiplier"] = em
        out["ROE"] = roe
        out["ROA"] = roa
        out["Asset_Turnover"] = at
    except Exception:
        pass
    return out


def _compute_liquidity_leverage(curr_row: pd.Series, prev_row: pd.Series = None) -> dict:
    out = {
        "Current_Ratio": None,
        "Working_Capital": None,
        "Debt_to_Equity": None,
        "Liabilities_to_Assets": None,
        "LT_Debt_Trend": None,
    }
    try:
        ca = _v(curr_row.get("current_assets"))
        cl = _v(curr_row.get("current_liabilities"))
        ltd = _v(curr_row.get("long_term_debt"))
        liab = _v(curr_row.get("total_liabilities"))
        assets = _v(curr_row.get("total_assets"))
        eq = _v(curr_row.get("total_equity"))

        if ca is not None and cl is not None:
            out["Working_Capital"] = ca - cl
        out["Current_Ratio"] = _d(ca, cl)

        # Debt-to-equity: الأفضل LTD/EQ، وإن تعذّر نحط Liab/Assets كبديل مع وسم في الـ Opinions لاحقاً.
        dte = _d(ltd, eq)
        if dte is None:
            dte = _d(liab, assets)
        out["Debt_to_Equity"] = dte
        out["Liabilities_to_Assets"] = _d(liab, assets)

        if prev_row is not None:
            ltd_p = _v(prev_row.get("long_term_debt"))
            if ltd is not None and ltd_p not in (None, 0):
                out["LT_Debt_Trend"] = (ltd - ltd_p) / abs(ltd_p)
    except Exception:
        pass
    return out


def _compute_earnings_quality(curr_row: pd.Series) -> dict:
    out = {
        "OCF_to_NetIncome": None,
        "Accruals_to_Assets": None,
        "OCF_Margin": None,
    }
    try:
        ni = _v(curr_row.get("net_income"))
        ocf = _v(curr_row.get("operating_cash_flow"))
        assets = _v(curr_row.get("total_assets"))
        rev = _v(curr_row.get("revenue"))

        out["OCF_to_NetIncome"] = _d(ocf, ni)
        if out["OCF_to_NetIncome"] is None and ocf is not None and ni in (None, 0):
            # إذا NI غير متوفر/0 و OCF موجب: لا نعطي 1.0 بشكل مضلل
            out["OCF_to_NetIncome"] = None

        if ni is not None and ocf is not None:
            out["Accruals_to_Assets"] = _d((ni - ocf), assets)
        out["OCF_Margin"] = _d(ocf, rev)
    except Exception:
        pass
    return out


def _compute_efficiency_pack(curr_row: pd.Series) -> dict:
    out = {"Gross_Margin": None, "Operating_Margin": None, "Net_Margin": None}
    try:
        rev = _v(curr_row.get("revenue"))
        if rev in (None, 0):
            return out

        gp = _best_key(curr_row, ["gross_profit", "grossProfit"], default=None)
        op_inc = _best_key(curr_row, ["operating_income", "operatingIncome", "ebit"], default=None)
        ni = _v(curr_row.get("net_income"))

        out["Gross_Margin"] = _d(gp, rev)
        out["Operating_Margin"] = _d(op_inc, rev)
        out["Net_Margin"] = _d(ni, rev)
    except Exception:
        pass
    return out


def _compute_cashflow_pack(curr_row: pd.Series) -> dict:
    out = {"Free_Cash_Flow": None, "FCF_Margin": None, "FCF_to_NetIncome": None}
    try:
        ocf = _v(curr_row.get("operating_cash_flow"))
        capex = _best_key(curr_row, ["capex", "capital_expenditure", "capitalExpenditures"], default=None)
        rev = _v(curr_row.get("revenue"))
        ni = _v(curr_row.get("net_income"))

        if ocf is None:
            return out

        capex_out = abs(_safe_float_none(capex) or 0.0) if capex is not None else 0.0
        fcf = ocf - capex_out

        out["Free_Cash_Flow"] = fcf
        out["FCF_Margin"] = _d(fcf, rev)
        out["FCF_to_NetIncome"] = _d(fcf, ni)
    except Exception:
        pass
    return out


def _compute_growth_pack(curr_row: pd.Series, prev_row: pd.Series) -> dict:
    out = {"Revenue_Growth_YoY": None, "NetIncome_Growth_YoY": None}
    try:
        rev_c = _v(curr_row.get("revenue"))
        rev_p = _v(prev_row.get("revenue"))
        ni_c = _v(curr_row.get("net_income"))
        ni_p = _v(prev_row.get("net_income"))

        if rev_c is not None and rev_p not in (None, 0):
            out["Revenue_Growth_YoY"] = (rev_c - rev_p) / abs(rev_p)
        if ni_c is not None and ni_p not in (None, 0):
            out["NetIncome_Growth_YoY"] = (ni_c - ni_p) / abs(ni_p)
    except Exception:
        pass
    return out


def _compute_interest_coverage_best_effort(curr_row: pd.Series, yahoo_info: dict) -> dict:
    out = {"Interest_Coverage": None, "Interest_Coverage_Quality": "partial"}
    try:
        ebit = _best_key(curr_row, ["ebit", "operating_income", "operatingIncome"], default=None)
        ie = _best_key(curr_row, ["interest_expense", "interestExpense"], default=None)

        if ie in (None, 0):
            ie = _safe_float_none(yahoo_info.get("interestExpense"))

        if ebit is not None and ie not in (None, 0):
            out["Interest_Coverage"] = ebit / abs(ie)
            out["Interest_Coverage_Quality"] = "full"
    except Exception:
        pass
    return out
