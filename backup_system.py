"""Tenant-safe Excel backup generation."""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone
from typing import Dict

import pandas as pd

from database import fetch_table
from tenant_scope import current_tenant

logger = logging.getLogger("osoli.backup")

BACKUP_TABLES: Dict[str, str] = {
    "trades": "الصفقات",
    "deposits": "الإيداعات",
    "withdrawals": "السحوبات",
    "returnsgrants": "العوائد",
    "watchlist": "قائمة_المراقبة",
    "investmentthesis": "الأطروحات",
    "ai_user_rules": "قواعد_المستشار",
    "ai_signals": "إشارات_المستشار",
    "ai_outcomes": "نتائج_الإشارات",
}

_INTERNAL_COLUMNS = {"user_id", "portfolio_id"}
_FORMULA_PREFIXES = ("=", "+", "-", "@")


def _safe_excel_value(value):
    """Prevent spreadsheet formula execution in user-entered text cells."""
    if isinstance(value, str) and value.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def _prepare_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    output = frame.copy()
    output = output.drop(
        columns=[column for column in _INTERNAL_COLUMNS if column in output.columns],
        errors="ignore",
    )
    object_columns = output.select_dtypes(include=["object", "string"]).columns
    for column in object_columns:
        output[column] = output[column].map(_safe_excel_value)
    return output


def _auto_width(writer: pd.ExcelWriter, sheet_name: str, frame: pd.DataFrame) -> None:
    worksheet = writer.sheets[sheet_name]
    worksheet.freeze_panes(1, 0)
    worksheet.autofilter(0, 0, max(0, len(frame)), max(0, len(frame.columns) - 1))
    for index, column in enumerate(frame.columns):
        series = frame[column].astype(str) if not frame.empty else pd.Series(dtype=str)
        value_width = int(series.map(len).max()) if not series.empty else 0
        width = min(max(len(str(column)), value_width) + 2, 45)
        worksheet.set_column(index, index, max(10, width))


def generate_full_backup():
    """Create an Excel export containing only the active tenant's private data."""
    tenant = current_tenant()
    if tenant is None:
        logger.warning("backup requested without tenant context")
        return None, None

    output = io.BytesIO()
    generated_at = datetime.now(timezone.utc).replace(microsecond=0)
    try:
        with pd.ExcelWriter(
            output,
            engine="xlsxwriter",
            date_format="yyyy-mm-dd",
            datetime_format="yyyy-mm-dd hh:mm:ss",
            engine_kwargs={"options": {"strings_to_formulas": False, "strings_to_urls": False}},
        ) as writer:
            metadata = pd.DataFrame(
                [
                    {"الحقل": "المستخدم", "القيمة": tenant.username},
                    {"الحقل": "تاريخ الإنشاء UTC", "القيمة": generated_at.isoformat()},
                    {"الحقل": "نوع النسخة", "القيمة": "بيانات المحفظة النشطة فقط"},
                    {"الحقل": "إصدار المخطط", "القيمة": "tenant-v2"},
                ]
            )
            metadata.to_excel(writer, sheet_name="معلومات", index=False)
            _auto_width(writer, "معلومات", metadata)

            exported = 0
            for table_name, sheet_name in BACKUP_TABLES.items():
                try:
                    frame = _prepare_frame(fetch_table(table_name))
                except Exception:
                    logger.exception("failed to export table %s", table_name)
                    continue
                if frame.empty:
                    continue
                frame.to_excel(writer, sheet_name=sheet_name[:31], index=False)
                _auto_width(writer, sheet_name[:31], frame)
                exported += 1

            if exported == 0:
                empty = pd.DataFrame(
                    {"الحالة": ["لا توجد بيانات خاصة في المحفظة النشطة"]}
                )
                empty.to_excel(writer, sheet_name="لا_توجد_بيانات", index=False)
                _auto_width(writer, "لا_توجد_بيانات", empty)

        output.seek(0)
        timestamp = generated_at.strftime("%Y-%m-%d_%H-%M")
        safe_username = "".join(
            char for char in tenant.username if char.isalnum() or char in {"_", "-"}
        )[:30] or "user"
        return output, f"Osoli_{safe_username}_{timestamp}.xlsx"
    except Exception:
        logger.exception("backup generation failed")
        return None, None
