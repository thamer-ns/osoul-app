# financial_analysis/quality_gate.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from market_data import get_ticker_symbol
from .store import get_stored_financials_df
from .utils import _safe_float_none, _is_missing


ESSENTIAL_FIELDS = [
    # income statement
    "revenue",
    "net_income",
    # balance sheet
    "total_assets",
    "total_liabilities",
    "total_equity",
    # cashflow
    "operating_cash_flow",
]

OPTIONAL_BUT_IMPORTANT = [
    "current_assets",
    "current_liabilities",
    "long_term_debt",
    "capex",
]


def _is_none_or_nan(x: Any) -> bool:
    try:
        return x is None or (isinstance(x, float) and pd.isna(x)) or (isinstance(x, pd.Timestamp) and pd.isna(x))
    except Exception:
        return x is None


def _num(x: Any) -> Optional[float]:
    return _safe_float_none(x)


def _bad_sign(value: Optional[float], field: str) -> bool:
    # revenue should not be negative; assets/liab should not be negative in normal statements
    if value is None:
        return False
    if field in ("revenue", "total_assets", "total_liabilities", "current_assets", "current_liabilities", "total_equity", "long_term_debt"):
        return value < 0
    return False


def _ratio_gap(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None:
        return None
    denom = abs(a) if abs(a) > 1e-9 else None
    if denom is None:
        return None
    return abs(a - b) / denom


def evaluate_financial_data_quality(
    symbol: str,
    preferred_period: str = "Annual",
    min_rows: int = 2,
) -> Dict[str, Any]:
    """
    بوابة جودة بيانات القوائم المالية قبل التحليل الأساسي/المستشار.

    المخرجات:
      {
        pass: bool,
        score: int (0..100),
        period_used: "Annual"|"Quarterly"|"None",
        issues: [str],
        missing_fields: [str],
        coverage: {field: pct_available},
        meta: {...}
      }

    ملاحظة:
    - لا تحاول الجلب من الإنترنت هنا (Gate يجب أن يكون سريعاً).
    - يعتمد على البيانات المخزّنة في DB عبر get_stored_financials_df.
    """
    out: Dict[str, Any] = {
        "pass": False,
        "score": 0,
        "period_used": "None",
        "issues": [],
        "missing_fields": [],
        "coverage": {},
        "meta": {},
    }

    try:
        symbol = get_ticker_symbol(symbol)
    except Exception:
        symbol = str(symbol or "").strip()

    # Load statements
    df = get_stored_financials_df(symbol, preferred_period)
    period_used = preferred_period
    if df.empty and preferred_period != "Quarterly":
        df = get_stored_financials_df(symbol, "Quarterly")
        period_used = "Quarterly"

    out["period_used"] = period_used if not df.empty else "None"

    if df.empty:
        out["issues"].append("لا توجد قوائم مالية مخزّنة لهذا الرمز (Annual/Quarterly).")
        out["missing_fields"] = ESSENTIAL_FIELDS.copy()
        out["score"] = 0
        out["pass"] = False
        return out

    # Ensure we have enough history for trend checks (best-effort)
    if len(df) < min_rows:
        out["issues"].append(f"عدد الفترات المتاحة قليل ({len(df)}) — قد يضعف الثقة في النمو/الاتجاهات.")
    out["meta"]["rows"] = int(len(df))

    # Coverage per field across available rows (top N rows)
    sample = df.head(max(min_rows, min(6, len(df))))
    cov = {}
    for f in ESSENTIAL_FIELDS + OPTIONAL_BUT_IMPORTANT:
        present = 0
        total = len(sample)
        if f in sample.columns:
            for _, r in sample.iterrows():
                v = r.get(f)
                if not _is_none_or_nan(v) and not _is_missing(v):
                    present += 1
        cov[f] = 0 if total == 0 else round(100.0 * present / total, 1)
    out["coverage"] = cov

    # Missing essentials in current (most recent row)
    curr = df.iloc[0]
    missing = []
    for f in ESSENTIAL_FIELDS:
        if f not in df.columns:
            missing.append(f)
            continue
        v = curr.get(f)
        if _is_none_or_nan(v) or _is_missing(v):
            missing.append(f)
    out["missing_fields"] = missing

    # Score starts at 100, subtract penalties
    score = 100

    # Period penalty
    if period_used == "Quarterly":
        score -= 10
        out["issues"].append("تم استخدام بيانات ربع سنوية لعدم توفر السنوية — قد تختلف بعض النسب.")

    # Missing essentials penalty
    if missing:
        score -= min(60, 15 * len(missing))
        out["issues"].append("نقص في حقول أساسية: " + ", ".join(missing))

    # Basic sign sanity
    sign_issues = []
    for f in ESSENTIAL_FIELDS + OPTIONAL_BUT_IMPORTANT:
        if f not in df.columns:
            continue
        v = _num(curr.get(f))
        if _bad_sign(v, f):
            sign_issues.append(f)
    if sign_issues:
        score -= min(20, 5 * len(sign_issues))
        out["issues"].append("قيم سالبة غير منطقية في: " + ", ".join(sign_issues))

    # Balance sheet consistency: Assets ≈ Liabilities + Equity
    ta = _num(curr.get("total_assets"))
    tl = _num(curr.get("total_liabilities"))
    te = _num(curr.get("total_equity"))
    if ta is not None and tl is not None and te is not None and ta > 0:
        gap = _ratio_gap(ta, (tl + te))
        if gap is not None:
            out["meta"]["bs_gap_ratio"] = float(gap)
            # allow some tolerance because sources may differ / rounding / minority interest
            if gap > 0.15:
                score -= 20
                out["issues"].append("عدم اتساق الميزانية: الأصول بعيدة عن (الالتزامات + حقوق الملكية) بنسبة كبيرة.")
            elif gap > 0.07:
                score -= 10
                out["issues"].append("اتساق الميزانية متوسط: يوجد فرق ملحوظ بين الأصول و(الالتزامات + حقوق الملكية).")
    else:
        # if any missing, issue already covered by missing essentials
        pass

    # Trend sanity: avoid extreme jumps (best-effort)
    # Revenue jump > 300% or collapse > 80% triggers warning
    if len(df) >= 2 and "revenue" in df.columns:
        rev_c = _num(curr.get("revenue"))
        rev_p = _num(df.iloc[1].get("revenue"))
        if rev_c is not None and rev_p is not None and abs(rev_p) > 1e-9:
            chg = (rev_c - rev_p) / abs(rev_p)
            out["meta"]["rev_change_yoy"] = float(chg)
            if chg > 3.0 or chg < -0.8:
                score -= 10
                out["issues"].append("قفزة/هبوط غير معتاد في الإيرادات بين آخر فترتين — تحقق من المصدر/الوحدة/التواريخ.")

    # Operating cash flow vs net income sanity (not a fail, but warning if wildly divergent)
    ni = _num(curr.get("net_income"))
    ocf = _num(curr.get("operating_cash_flow"))
    if ni is not None and ocf is not None and abs(ni) > 1e-9:
        ratio = ocf / ni
        out["meta"]["ocf_to_ni"] = float(ratio)
        if ratio > 10 or ratio < -10:
            score -= 5
            out["issues"].append("فرق كبير جداً بين OCF وصافي الربح — قد تكون البيانات غير مكتملة أو يوجد بنود غير متكررة.")

    score = int(max(0, min(100, score)))
    out["score"] = score

    # PASS criteria
    # - no missing essential fields in current row
    # - score >= 60
    out["pass"] = (len(missing) == 0) and (score >= 60)

    if not out["pass"]:
        out["issues"].insert(0, "⛔ بوابة جودة البيانات: فشل التحقق — سيتم حجب الرأي النهائي حتى اكتمال/اتساق القوائم.")

    return out
