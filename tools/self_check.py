"""
tools/self_check.py
تشخيص سريع للمشروع بدون تشغيل Streamlit.
يشيك:
- وجود الملفات الأساسية
- عدم وجود أخطاء Syntax
- تقرير عن __pycache__
- تقرير عن الاستيرادات الداخلية (بدون تنفيذ imports التي تحتاج streamlit)
"""

from __future__ import annotations
import os
import ast
from pathlib import Path
from typing import List, Tuple, Dict, Set

PROJECT_ROOT = Path(__file__).resolve().parents[1]

REQUIRED_PATHS = [
    "app.py",
    "views/__init__.py",
    "ai_engine_core/reporting.py",
    "ai_engine_core/packs.py",
    "financial_analysis/__init__.py",
    "database.py",
    "market_data.py",
    "requirements.txt",
]

def list_py_files() -> List[Path]:
    return [p for p in PROJECT_ROOT.rglob("*.py") if ".venv" not in str(p)]

def check_required() -> List[str]:
    missing = []
    for rel in REQUIRED_PATHS:
        if not (PROJECT_ROOT / rel).exists():
            missing.append(rel)
    return missing

def check_syntax(py_files: List[Path]) -> List[Tuple[str, str, int]]:
    errs = []
    for p in py_files:
        try:
            ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError as e:
            errs.append((str(p.relative_to(PROJECT_ROOT)), e.msg, int(e.lineno or 0)))
    return errs

def find_pycache() -> List[str]:
    hits = []
    for p in PROJECT_ROOT.rglob("__pycache__"):
        hits.append(str(p.relative_to(PROJECT_ROOT)))
    return sorted(hits)

def build_import_graph(py_files: List[Path]) -> Dict[str, Set[str]]:
    # crude static graph: module -> imported module names
    graph: Dict[str, Set[str]] = {}
    for p in py_files:
        rel = p.relative_to(PROJECT_ROOT)
        mod = ".".join(rel.with_suffix("").parts)
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        try:
            tree = ast.parse(p.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            continue
        imports: Set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                for a in n.names:
                    imports.add(a.name)
            elif isinstance(n, ast.ImportFrom):
                if n.module:
                    imports.add(n.module)
        graph[mod] = imports
    return graph

def main() -> int:
    print("="*72)
    print("Osoli Self Check")
    print("Project:", PROJECT_ROOT)
    print("="*72)

    missing = check_required()
    if missing:
        print("❌ Missing required files:")
        for m in missing:
            print(" -", m)
    else:
        print("✅ Required files: OK")

    py_files = list_py_files()
    syn = check_syntax(py_files)
    if syn:
        print("\n❌ Syntax errors:")
        for f, msg, ln in syn:
            print(f" - {f}:{ln} -> {msg}")
    else:
        print("\n✅ Syntax: OK")

    pc = find_pycache()
    if pc:
        print("\n⚠️ __pycache__ folders found (recommended to delete before release):")
        for x in pc:
            print(" -", x)
    else:
        print("\n✅ No __pycache__ folders.")

    graph = build_import_graph(py_files)
    # quick: show top-level modules count
    print("\n📦 Python modules scanned:", len(graph))

    print("\nDone.")
    return 0 if (not missing and not syn) else 2

if __name__ == "__main__":
    raise SystemExit(main())
