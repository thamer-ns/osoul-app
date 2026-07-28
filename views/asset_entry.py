"""Embedded asset-entry forms for the unified portfolios hub.

The public navigation no longer exposes a standalone add page. Existing
``إضافة سهم`` and ``إضافة صك`` buttons inside each portfolio route back to the
hub with a one-shot flag, and this module renders the correct locked-down form
for the active portfolio section.
"""
from __future__ import annotations

import hashlib
import logging
import re
from datetime import date
from typing import Any

import streamlit as st

from data_source import get_company_details
from database import execute_query
from security import validate_trade_inputs
from tenant_scope import current_tenant
from views.shared import _normalize_symbol

LOGGER = logging.getLogger(__name__)
_SECTION_STRATEGY = {
    "spec": "مضاربة",
    "invest": "استثمار",
    "sukuk": "صكوك",
}


def _stock_company(symbol: str) -> tuple[str, str]:
    try:
        info = get_company_details(symbol)
        if isinstance(info, dict):
            return (
                str(info.get("name") or info.get("Name") or symbol),
                str(info.get("sector") or info.get("Sector") or ""),
            )
        if isinstance(info, (tuple, list)) and len(info) >= 2:
            return str(info[0] or symbol), str(info[1] or "")
        if info:
            return str(info), ""
    except Exception:
        LOGGER.debug("Company metadata unavailable for %s", symbol, exc_info=True)
    return symbol, ""


def _sukuk_reference(value: Any, name: str) -> str:
    """Return a stable, DB-safe sukuk reference without stock normalization."""
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "-", str(value or "").strip().upper())
    cleaned = cleaned.strip("-_")[:48]
    if cleaned:
        return cleaned
    digest = hashlib.sha256(name.strip().encode("utf-8")).hexdigest()[:10].upper()
    return f"SUKUK-{digest}"


def _save_asset(
    *,
    symbol: str,
    name: str,
    sector: str,
    asset_type: str,
    quantity: float,
    price: float,
    strategy: str,
    bought_at: date,
) -> bool:
    tenant = current_tenant()
    if tenant is None:
        st.error("تعذر تحديد المحفظة النشطة بأمان.")
        return False
    saved = execute_query(
        "INSERT INTO trades "
        "(symbol, company_name, sector, asset_type, quantity, "
        "entry_price, current_price, strategy, status, date, "
        "created_at, updated_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'Open',%s,"
        "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
        (
            symbol,
            name,
            sector,
            asset_type,
            quantity,
            price,
            price,
            strategy,
            str(bought_at),
        ),
    )
    if not saved:
        st.error("تعذر حفظ الأصل في المحفظة. لم تتغير البيانات.")
        return False
    st.cache_data.clear()
    st.session_state.pop("_portfolio_add_open_once", None)
    st.session_state["_portfolio_asset_flash"] = (
        f"تمت إضافة {name} إلى محفظة {strategy}"
    )
    return True


def _render_stock_form(section: str) -> None:
    strategy = _SECTION_STRATEGY[section]
    with st.form(f"embedded_stock_entry_{section}", clear_on_submit=False):
        st.markdown(f"#### ➕ إضافة سهم إلى محفظة {strategy}")
        st.caption("نوع المحفظة محدد مسبقًا ولن يُحفظ السهم في قسم آخر.")
        c1, c2 = st.columns([1.2, 1])
        raw_symbol = c1.text_input(
            "رمز السهم",
            placeholder="مثال: 1120 أو 1120.SR",
            key=f"embedded_symbol_{section}",
        )
        bought_at = c2.date_input(
            "تاريخ الشراء",
            date.today(),
            key=f"embedded_stock_date_{section}",
        )
        c3, c4 = st.columns(2)
        quantity = c3.number_input(
            "الكمية",
            min_value=0.001,
            step=1.0,
            key=f"embedded_stock_qty_{section}",
        )
        price = c4.number_input(
            "سعر الشراء للوحدة",
            min_value=0.01,
            step=0.01,
            key=f"embedded_stock_price_{section}",
        )
        submitted = st.form_submit_button(
            f"حفظ السهم في محفظة {strategy}",
            type="primary",
            use_container_width=True,
        )
    if not submitted:
        return
    valid, message = validate_trade_inputs(quantity, price)
    if not valid:
        st.error(message)
        return
    symbol = _normalize_symbol(raw_symbol)
    if not symbol or symbol == ".SR":
        st.error("أدخل رمز سهم صحيحًا مثل 1120 أو 1120.SR.")
        return
    name, sector = _stock_company(symbol)
    if _save_asset(
        symbol=symbol,
        name=name,
        sector=sector,
        asset_type="Stock",
        quantity=float(quantity),
        price=float(price),
        strategy=strategy,
        bought_at=bought_at,
    ):
        st.rerun()


def _render_sukuk_form() -> None:
    with st.form("embedded_sukuk_entry", clear_on_submit=False):
        st.markdown("#### ➕ إضافة صك إلى محفظة الصكوك")
        st.caption(
            "اسم الصك مطلوب، والمرجع اختياري. عند تركه فارغًا ينشئ أصولي مرجعًا ثابتًا تلقائيًا."
        )
        c1, c2 = st.columns([1.3, 1])
        name = c1.text_input(
            "اسم الصك",
            placeholder="مثال: صكوك الشركة السعودية — الإصدار الأول",
            key="embedded_sukuk_name",
        )
        reference = c2.text_input(
            "رمز أو مرجع الصك — اختياري",
            placeholder="SUKUK-001",
            key="embedded_sukuk_reference",
        )
        c3, c4, c5 = st.columns(3)
        quantity = c3.number_input(
            "عدد الصكوك",
            min_value=0.001,
            step=1.0,
            key="embedded_sukuk_qty",
        )
        unit_cost = c4.number_input(
            "تكلفة الوحدة",
            min_value=0.01,
            step=10.0,
            key="embedded_sukuk_cost",
        )
        bought_at = c5.date_input(
            "تاريخ الشراء",
            date.today(),
            key="embedded_sukuk_date",
        )
        submitted = st.form_submit_button(
            "حفظ الصك في محفظة الصكوك",
            type="primary",
            use_container_width=True,
        )
    if not submitted:
        return
    clean_name = str(name or "").strip()
    if not clean_name:
        st.error("أدخل اسم الصك.")
        return
    valid, message = validate_trade_inputs(quantity, unit_cost)
    if not valid:
        st.error(message)
        return
    symbol = _sukuk_reference(reference, clean_name)
    if _save_asset(
        symbol=symbol,
        name=clean_name,
        sector="صكوك ودخل ثابت",
        asset_type="Sukuk",
        quantity=float(quantity),
        price=float(unit_cost),
        strategy="صكوك",
        bought_at=bought_at,
    ):
        st.rerun()


def render_embedded_asset_entry(section: str) -> None:
    """Render the active portfolio's form only after its internal add button."""
    if section not in _SECTION_STRATEGY:
        return
    flash = st.session_state.pop("_portfolio_asset_flash", None)
    if flash:
        st.success(str(flash))
    if not bool(st.session_state.get("_portfolio_add_open_once")):
        return

    with st.container(key=f"embedded_asset_entry_{section}"):
        if st.button(
            "إلغاء الإضافة",
            icon="✖️",
            key=f"cancel_embedded_asset_{section}",
        ):
            st.session_state.pop("_portfolio_add_open_once", None)
            st.rerun()
        if section == "sukuk":
            _render_sukuk_form()
        else:
            _render_stock_form(section)
