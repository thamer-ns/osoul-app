"""Advanced technical indicators used by the UI and AI engine.

The public builder adds pack identity metadata expected by the report cache while
preserving the corrected v2 implementation and schema.
"""
from __future__ import annotations

from typing import Any

from .advanced_v2 import compute_advanced_technical_pack as _compute_advanced_technical_pack


def compute_advanced_technical_pack(*args: Any, **kwargs: Any) -> dict[str, Any]:
    pack = _compute_advanced_technical_pack(*args, **kwargs)
    if not isinstance(pack, dict):
        return {
            "name": "Advanced Technical Pack v2",
            "errors": ["تعذر بناء حزمة المؤشرات المتقدمة"],
        }
    pack.setdefault("name", "Advanced Technical Pack v2")
    meta = pack.get("meta")
    if isinstance(meta, dict):
        meta.setdefault("schema_version", "2.1")
        meta.setdefault("confirmation", "close")
    return pack


__all__ = ["compute_advanced_technical_pack"]
