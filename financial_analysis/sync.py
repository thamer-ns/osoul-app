# financial_analysis/sync_full.py
from __future__ import annotations

from typing import Dict, Any, Tuple, List
from datetime import datetime

import pandas as pd

from market_data import get_ticker_symbol
from osoli_logging import log_exception

from .yahoo_data import fetch_full_financial_statements_yahoo_json
from .store_full import save_full_statement_record


def _to_thousands(d: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (d or {}).items():
        if isinstance(v, (int, float)) and v is not None:
            out[k] = float(v) / 1000.0
        else:
            out[k] = v
    return out


def _calc_ttm_from_quarters(q_records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Sum last 4 quarters numeric keys."""
    if not q_records:
        return {}
    # assume q_records sorted desc by date
    last4 = q_records[:4]
    sums: Dict[str, float] = {}
    for rec in last4:
        for k, v in rec.items():
            if isinstance(v, (int, float)):
                sums[k] = sums.get(k, 0.0) + float(v)
    return sums


def sync_full_yahoo(symbol: str, include_ttm: bool = True) -> Tuple[bool, str]:
    """Fetch full statements (all line-items) annual+quarterly from Yahoo JSON and store them in DB.

    - Stores numbers in **thousands** to match Yahoo UI label 'جميع الأرقام بالآلاف'
    - Computes TTM:
        * income/cashflow: sum last 4 quarters per line-item
        * balance: latest quarter snapshot
    """
    sym = get_ticker_symbol(symbol)
    try:
        payload = fetch_full_financial_statements_yahoo_json(sym) or {}
    except Exception as e:
        log_exception(e, f"FullStatements fetch failed: {sym}", level="ERROR")
        return False, "فشل جلب القوائم الكاملة من Yahoo."

    saved = 0
    notes: List[str] = []

    def _save(statement: str, period_type: str, as_of: str, data: Dict[str, Any]):
        nonlocal saved
        ok = save_full_statement_record(
            sym,
            statement=statement,
            period_type=period_type,
            as_of=as_of,
            data=_to_thousands(data),
            scale="thousands",
            source="YahooJSON",
        )
        if ok:
            saved += 1

    # payload format: {statement: {Annual:[{date,data}], Quarterly:[...]} }
    for statement in ("income", "balance", "cashflow"):
        obj = payload.get(statement) or {}
        for ptype in ("Annual", "Quarterly"):
            rows = obj.get(ptype) or []
            for row in rows:
                as_of = str(row.get("date") or "")
                data = row.get("data") or {}
                if as_of and isinstance(data, dict) and data:
                    _save(statement, ptype, as_of, data)

        # TTM
        if include_ttm:
            qrows = obj.get("Quarterly") or []
            # ensure desc sort by date
            try:
                qrows_sorted = sorted(qrows, key=lambda r: r.get("date") or "", reverse=True)
            except Exception:
                qrows_sorted = qrows

            if statement in ("income", "cashflow"):
                ttm_data = _calc_ttm_from_quarters([r.get("data") or {} for r in qrows_sorted if isinstance(r, dict)])
                if ttm_data:
                    as_of = (qrows_sorted[0].get("date") if qrows_sorted else None) or datetime.now().strftime("%Y-%m-%d")
                    _save(statement, "TTM", str(as_of), ttm_data)
            else:
                # balance: latest quarter snapshot
                if qrows_sorted:
                    latest = qrows_sorted[0]
                    as_of = str(latest.get("date") or datetime.now().strftime("%Y-%m-%d"))
                    data = latest.get("data") or {}
                    if isinstance(data, dict) and data:
                        _save(statement, "TTM", as_of, data)

    if saved == 0:
        return False, "تم الجلب لكن لم يتم حفظ أي سجل (قد تكون البيانات غير متاحة لهذا الرمز)."
    return True, f"تم حفظ {saved} سجل للقوائم الكاملة (سنوي/ربع سنوي/TTM) بوحدة الآلاف."
