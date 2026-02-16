"""Create a sanitized release zip (no secrets, env files, caches).

Usage:
    python scripts/sanitize_release.py --src . --out osoul-app-main_sanitized.zip

This is meant for sharing the project safely.
"""

from __future__ import annotations

import argparse
import os
import shutil
import tempfile
import zipfile
from pathlib import Path


DEFAULT_EXCLUDES = {
    ".streamlit/secrets.toml",
    ".env",
    ".env.*",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "backups",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
}


def should_exclude(rel_posix: str) -> bool:
    rel_posix = rel_posix.lstrip("/")
    # direct match
    if rel_posix in DEFAULT_EXCLUDES:
        return True
    # folder match
    parts = rel_posix.split("/")
    if "__pycache__" in parts:
        return True
    # simple glob-like checks
    for pat in DEFAULT_EXCLUDES:
        if pat.startswith("*.") and rel_posix.endswith(pat[1:]):
            return True
        if pat.endswith(".*") and Path(rel_posix).name.startswith(pat[:-2]):
            return True
    return False


def build_sanitized_zip(src: Path, out_zip: Path) -> None:
    src = src.resolve()
    out_zip = out_zip.resolve()

    with tempfile.TemporaryDirectory(prefix="osoul_sanitized_") as td:
        stage = Path(td) / src.name
        shutil.copytree(src, stage, dirs_exist_ok=True)

        # remove excluded paths
        for path in list(stage.rglob("*")):
            rel = path.relative_to(stage).as_posix()
            if should_exclude(rel):
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    try:
                        path.unlink()
                    except FileNotFoundError:
                        pass

        # Ensure secrets template exists
        tmpl = stage / ".streamlit" / "secrets.example.toml"
        tmpl.parent.mkdir(exist_ok=True)
        if not tmpl.exists():
            tmpl.write_text(
                'DATABASE_URL = "postgresql://USER:PASSWORD@HOST:PORT/DBNAME"\n'
                'AUTH_SECRET = "PUT_A_STRONG_SECRET_HERE"\n'
                'TWELVEDATA_API_KEY = "YOUR_API_KEY"\n',
                encoding="utf-8",
            )

        # zip it
        if out_zip.exists():
            out_zip.unlink()
        with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
            for file in stage.rglob("*"):
                if file.is_file():
                    z.write(file, file.relative_to(stage.parent).as_posix())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=".", help="Project folder to sanitize")
    ap.add_argument("--out", default="osoul-app-main_sanitized.zip", help="Output zip path")
    args = ap.parse_args()

    build_sanitized_zip(Path(args.src), Path(args.out))
    print(f"Created: {Path(args.out).resolve()}")


if __name__ == "__main__":
    main()