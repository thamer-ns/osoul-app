# financial_analysis/data_quality.py
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from osoli_logging import log_exception
from .store import fetch_full_statement_records, has_full_statement, get_stored_financials_df
from market_data import get_ticker_symbol


def _to_numeric_series(s: pd.Series) -> pd.Series:
    out = pd.to_numeric(s, errors="coerce")
    return out


def _pick_line_item(df: pd.DataFrame, candidates: List[str]) -> Tuple[Optional[str], Optional[pd.Series]]:
    """Pick the first matching line item (case-insensitive) and return (name, series)."""
    if df is None or df.empty:
        return None, None
    idx = [str(i) for i in df.index]
    idx_l = [i.lower().strip() for i in idx]

    for c in candidates:
        c_l = c.lower().strip()
        # exact
        if c_l in idx_l:
            i = idx[idx_l.index(c_l)]
            return i, _to_numeric_series(df.loc[i])
    # fuzzy contains (prefer shorter candidate hits)
    for c in candidates:
        c_l = c.lower().strip()
        hits = [idx[j] for j, il in enumerate(idx_l) if c_l in il]
        if hits:
            # prefer the smallest label (often the canonical one)
            hits_sorted = sorted(hits, key=lambda x: len(str(x)))
            i = hits_sorted[0]
            return i, _to_numeric_series(df.loc[i])
    return None, None


def _series_health_metrics(x: pd.Series) -> Dict[str, Any]:
    x = x.dropna()
    if x.empty:
        return {"n": 0}

    # sort by column labels (dates) if possible
    try:
        x2 = x.copy()
        x2.index = pd.to_datetime(x2.index, errors="coerce")
        x2 = x2.sort_index()
        x = x2
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/data_quality.py:55')

    # pct change stability
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = x.pct_change().replace([np.inf, -np.inf], np.nan).dropna()

    jumps_300 = int((pct.abs() > 3.0).sum()) if not pct.empty else 0  # > 300%
    jumps_100 = int((pct.abs() > 1.0).sum()) if not pct.empty else 0  # > 100%
    sign_flips = int(((x.shift(1) * x) < 0).sum()) if len(x) >= 2 else 0

    return {
        "n": int(len(x)),
        "jumps_gt_100pct": jumps_100,
        "jumps_gt_300pct": jumps_300,
        "sign_flips": sign_flips,
        "min": float(np.nanmin(x.values)),
        "max": float(np.nanmax(x.values)),
    }


def assess_fundamental_quality(
    symbol: str,
    period_type: str = "Annual",
    *,
    scale: str = "thousands",
) -> Dict[str, Any]:
    """Assess fundamental data quality for a symbol using stored full statements.

    Returns dict:
      {score: 0..100, pass: bool, issues: [..], metrics: {...}}
    """
    issues: List[str] = []
    metrics: Dict[str, Any] = {}

    try:
        sym = get_ticker_symbol(symbol)
    except Exception:
        sym = str(symbol or "").strip()

    ptype = str(period_type or "Annual").strip()
    ptype = "TTM" if ptype.upper() == "TTM" else ptype.title()
    if ptype not in ("Annual", "Quarterly", "TTM"):
        ptype = "Annual"

    sc = str(scale or "thousands").strip().lower()
    if sc not in ("raw", "thousands"):
        sc = "thousands"

    # availability
    try:
        have_income = has_full_statement(sym, "income", ptype, scale=sc)
        have_cash = has_full_statement(sym, "cashflow", ptype, scale=sc)
        have_balance = has_full_statement(sym, "balance", ptype, scale=sc)
    except Exception:
        have_income = have_cash = have_balance = False

    if not (have_income or have_cash or have_balance):
        # Fallback to summary table (financialstatements) if full statements are not stored
        try:
            sdf = get_stored_financials_df(sym, ptype)
        except Exception:
            sdf = pd.DataFrame()

        if sdf is not None and not sdf.empty:
            # Basic coverage check on required columns
            req = ["revenue", "net_income", "total_assets", "total_liabilities", "total_equity", "operating_cash_flow"]
            missing_cols = [c for c in req if c not in sdf.columns]
            score = 100
            issues2 = []
            if missing_cols:
                issues2.append(f"نقص أعمدة أساسية في جدول الملخص: {', '.join(missing_cols)}")
                score -= min(60, 10 * len(missing_cols))
            # last row completeness
            try:
                last = sdf.sort_values("date").iloc[-1]
                miss = [c for c in req if pd.isna(last.get(c, None)) or float(last.get(c, 0) or 0) == 0.0]
                if miss:
                    issues2.append(f"نقص/صفر في أحدث فترة (ملخص): {', '.join(miss)}")
                    score -= min(50, 8 * len(miss))
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/data_quality.py:135')
            score = int(max(0, min(100, round(score))))
            passed = score >= 55
            return {
                "score": score,
                "pass": passed,
                "issues": issues2[:25] if issues2 else ["بيانات الملخص متوفرة لكن القوائم الكاملة غير مخزنة."],
                "metrics": {"symbol": sym, "period_type": ptype, "scale": sc, "fallback": "summary"},
            }

        return {
            "score": 0,
            "pass": False,
            "issues": ["لا توجد بيانات قوائم مالية مخزّنة لهذا الرمز (income/cashflow/balance) ولا بيانات ملخص."],
            "metrics": {"symbol": sym, "period_type": ptype, "scale": sc},
        }
    # fetch
    income = cash = balance = pd.DataFrame()
    try:
        if have_income:
            income = fetch_full_statement_records(sym, "income", ptype, scale=sc)
        if have_cash:
            cash = fetch_full_statement_records(sym, "cashflow", ptype, scale=sc)
        if have_balance:
            balance = fetch_full_statement_records(sym, "balance", ptype, scale=sc)
    except Exception as e:
        log_exception(e, "fundamental_quality: fetch_full_statement_records failed", level="WARNING")

    score = 100

    if income is None or income.empty:
        issues.append("قائمة الدخل غير متوفرة أو فارغة.")
        score -= 25
    if cash is None or cash.empty:
        issues.append("قائمة التدفقات النقدية غير متوفرة أو فارغة.")
        score -= 25
    if balance is None or balance.empty:
        issues.append("قائمة المركز المالي غير متوفرة أو فارغة.")
        score -= 10

    # helper to compute coverage and anomalies
    found: Dict[str, Any] = {}
    health: Dict[str, Any] = {}

    # pick items
    # Revenue, NetIncome (income)
    rev_name, rev = _pick_line_item(income, ["TotalRevenue", "Revenue", "Total revenue", "Total Revenue"])
    ni_name, ni = _pick_line_item(income, ["NetIncome", "Net Income", "NetIncomeCommonStockholders", "Net income"])
    eps_name, eps = _pick_line_item(income, ["DilutedEPS", "BasicEPS", "EPS", "Diluted EPS", "Basic EPS"])

    # OCF, FCF (cashflow)
    ocf_name, ocf = _pick_line_item(cash, ["OperatingCashFlow", "Operating Cash Flow", "NetCashProvidedByOperatingActivities"])
    fcf_name, fcf = _pick_line_item(cash, ["FreeCashFlow", "Free Cash Flow", "FreeCashflow"])


    # Balance sheet items (for consistency)
    assets_name, assets = _pick_line_item(balance, ["TotalAssets", "Total Assets"])
    liab_name, liab = _pick_line_item(balance, ["TotalLiabilitiesNetMinorityInterest", "Total Liabilities", "TotalLiabilities"])
    eq_name, eq = _pick_line_item(balance, ["TotalEquityGrossMinorityInterest", "Total Stockholder Equity", "Stockholders Equity", "TotalEquity"])

    found.update({
        "revenue_item": rev_name,
        "net_income_item": ni_name,
        "eps_item": eps_name,
        "operating_cf_item": ocf_name,
        "free_cf_item": fcf_name,
        "assets_item": assets_name,
        "liabilities_item": liab_name,
        "equity_item": eq_name,
    })

    # compute metrics for each series
    series_map = {
        "revenue": rev,
        "net_income": ni,
        "eps": eps,
        "operating_cf": ocf,
        "free_cf": fcf,
        "assets": assets,
        "liabilities": liab,
        "equity": eq,
    }

    for k, s in series_map.items():
        if s is None:
            issues.append(f"تعذّر العثور على بند {k} داخل القوائم.")
            score -= 8
            continue
        hm = _series_health_metrics(s)
        health[k] = hm
        if hm.get("n", 0) < (3 if ptype in ("Annual", "TTM") else 4):
            issues.append(f"عدد الفترات المتاحة قليل لبند {k} (n={hm.get('n', 0)}).")
            score -= 8

        # Penalize extreme jumps
        j300 = int(hm.get("jumps_gt_300pct", 0) or 0)
        j100 = int(hm.get("jumps_gt_100pct", 0) or 0)
        flips = int(hm.get("sign_flips", 0) or 0)

        score -= min(20, j300 * 5)
        score -= min(12, max(0, j100 - j300) * 2)
        score -= min(10, flips * 2)

    
    # cross-consistency: Assets ≈ Liabilities + Equity (Balance sheet sanity)
    try:
        if (assets is not None) and (liab is not None) and (eq is not None):
            a2 = assets.dropna()
            l2 = liab.dropna()
            e2 = eq.dropna()
            common = a2.index.intersection(l2.index).intersection(e2.index)
            if len(common) >= 2:
                # check last 3 periods
                common = list(common)[-3:]
                bad = 0
                for d in common:
                    A = float(a2.loc[d])
                    L = float(l2.loc[d])
                    E = float(e2.loc[d])
                    if A == 0:
                        continue
                    gap = abs(A - (L + E)) / abs(A)
                    if gap > 0.15:
                        bad += 1
                if bad >= 1:
                    issues.append("عدم اتساق محتمل في الميزانية: الأصول لا تساوي (الالتزامات + حقوق الملكية) ضمن هامش مقبول.")
                    score -= min(15, bad * 7)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/data_quality.py:263')

# cross-consistency: net income vs operating CF
    try:
        if (ni is not None) and (ocf is not None):
            ni2 = ni.dropna()
            ocf2 = ocf.dropna()
            # align last 4 periods
            common = ni2.index.intersection(ocf2.index)
            if len(common) >= 3:
                ni_a = ni2.loc[common]
                ocf_a = ocf2.loc[common]
                # If NI positive but OCF strongly negative repeatedly -> flag
                bad = int(((ni_a > 0) & (ocf_a < 0)).sum())
                if bad >= 2:
                    issues.append("تناقض محتمل: صافي الربح موجب بينما التدفق التشغيلي سالب لعدة فترات (قد يشير لجودة أرباح منخفضة أو بيانات غير متسقة).")
                    score -= min(12, bad * 4)
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at financial_analysis/data_quality.py:281')

    score = int(max(0, min(100, round(score))))
    passed = score >= 55  # threshold

    metrics.update({
        "symbol": sym,
        "period_type": ptype,
        "scale": sc,
        "found_items": found,
        "health": health,
        "have_income": bool(have_income),
        "have_cashflow": bool(have_cash),
        "have_balance": bool(have_balance),
    })

    if not passed:
        issues.insert(0, "جودة البيانات الأساسية منخفضة؛ يفضّل عدم بناء قرار استثماري على هذا التحليل فقط.")

    return {"score": score, "pass": passed, "issues": issues[:25], "metrics": metrics}
