"""tools/cleanup.py

تنظيف اختياري (لا يغير منطق البرنامج) يساعدك قبل النشر:
- حذف __pycache__ وملفات .pyc
- (اختياري) أرشفة مجلدات يُحتمل أنها Dead Code مثل legacy/ و twelvedata/

الاستخدام:
  python tools/cleanup.py                 # يحذف __pycache__ فقط
  python tools/cleanup.py --archive-dead  # ينقل legacy/ و twelvedata/ إلى _archive/ بتاريخ اليوم

ملاحظة: النقل للأرشيف (وليس الحذف) لتفادي كسر أي اعتماد غير ظاهر.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def remove_pycache(root: Path) -> int:
    removed = 0
    for p in root.rglob("__pycache__"):
        try:
            shutil.rmtree(p)
            removed += 1
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at tools/cleanup.py:30')

    for p in root.rglob("*.pyc"):
        try:
            p.unlink()
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at tools/cleanup.py:36')
    return removed


def archive_dir(src: Path, archive_root: Path) -> bool:
    if not src.exists() or not src.is_dir():
        return False
    archive_root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.utcnow().strftime("%Y%m%d")
    dest = archive_root / f"{src.name}_{stamp}"
    if dest.exists():
        # Avoid collisions.
        dest = archive_root / f"{src.name}_{stamp}_2"
    shutil.move(str(src), str(dest))
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--archive-dead",
        action="store_true",
        help="Archive likely-dead directories (legacy/, twelvedata/) into _archive/",
    )
    args = ap.parse_args()

    print("=" * 72)
    print("Osoli Cleanup")
    print("Project:", PROJECT_ROOT)
    print("=" * 72)

    n = remove_pycache(PROJECT_ROOT)
    print(f"✅ Removed __pycache__ folders: {n}")

    if args.archive_dead:
        archive_root = PROJECT_ROOT / "_archive"
        archived = []
        for name in ("legacy", "twelvedata"):
            if archive_dir(PROJECT_ROOT / name, archive_root):
                archived.append(name)
        if archived:
            print("📦 Archived:", ", ".join(archived), "->", archive_root.relative_to(PROJECT_ROOT))
        else:
            print("ℹ️ Nothing to archive.")
    else:
        print("ℹ️ Dead-code archive skipped. (Use --archive-dead to archive legacy/ and twelvedata/)")

    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
