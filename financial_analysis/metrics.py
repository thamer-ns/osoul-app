# financial_analysis/metrics.py
from typing import Tuple, List

import pandas as pd
import yfinance as yf

from market_data import get_ticker_symbol
from .store import get_stored_financials_df
from .utils import _safe_float, _safe_div


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
        retained = 0.0

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

        if altz > 0:
            if altz >= 3.0:
                score += 2
                opinions.append("✅ Altman Z قوي (مخاطر إفلاس منخفضة)")
            elif altz < 1.8:
                score -= 2
                opinions.append("⛔ Altman Z منخفض (مخاطر أعلى)")
            if altq != "full":
                opinions.append("ℹ️ Altman Z محسوب بشكل جزئي حسب المتوفر")

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
    metrics = {
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

        dup = _compute_dupont(curr)
        liq = _compute_liquidity_leverage(curr, prev)
        eqy = _compute_earnings_quality(curr)

        metrics.update(dup)
        metrics.update(liq)
        metrics.update(eqy)

        metrics.update(_compute_valuation_pack(info))

        try:
            eps = _safe_float(info.get("trailingEps"))
            bvps = _safe_float(info.get("bookValue"))
            if eps > 0 and bvps > 0:
                metrics["Fair_Value_Graham"] = float((22.5 * eps * bvps) ** 0.5)
        except Exception:
            pass

        metrics.update(_compute_altman_z_best_effort(symbol, curr, info))
        metrics.update(_compute_sgr(metrics.get("ROE", 0.0), info))

        fscore10, rating, adv_ops = _score_fundamentals(metrics)

        if metrics["Piotroski_Score"] >= 7:
            metrics["Financial_Health"] = "جيد"
        elif metrics["Piotroski_Score"] <= 3:
            metrics["Financial_Health"] = "هش"
        else:
            metrics["Financial_Health"] = "متوسط"

        if ocf_c < 0:
            adv_ops.append("⚠️ التدفق النقدي التشغيلي سالب")

        if int(metrics.get("SGR_Estimated", 0)) == 1:
            adv_ops.append("ℹ️ SGR محسوب بافتراض payoutRatio (تقديري)")

        if _safe_float(metrics.get("PE_Trailing", 0)) == 0 and _safe_float(metrics.get("PEG", 0)) == 0:
            adv_ops.append("ℹ️ بيانات التقييم (PE/PEG) غير متوفرة من Yahoo")

        metrics["Rating"] = rating
        metrics["Score"] = int(max(fscore10, int(metrics.get("Piotroski_Score", 0) or 0)))
        metrics["Opinions"] = " | ".join([str(x) for x in adv_ops if str(x).strip()])[:1200]

    except Exception:
        pass

    return metrics


def get_fundamental_ratios(symbol):
    return get_advanced_fundamental_ratios(symbol)
