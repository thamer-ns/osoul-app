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


import ast

def check_missing_init_files(repo_root: Path) -> list[str]:
    """Warn if a directory looks like a Python package but has a misnamed _init_.py instead of __init__.py."""
    warnings = []
    for p in repo_root.rglob("_init_.py"):
        pkg_dir = p.parent
        if not (pkg_dir / "__init__.py").exists():
            warnings.append(str(p.relative_to(repo_root)))
    return sorted(set(warnings))

def check_relative_imports(py_files: list[Path], repo_root: Path) -> list[tuple[str, str, str]]:
    """Detect relative imports that point to missing modules (common on case-sensitive systems)."""
    problems: list[tuple[str, str, str]] = []
    for f in py_files:
        rel = str(f.relative_to(repo_root))
        try:
            src = f.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(src, filename=rel)
        except Exception as e:
            problems.append((rel, "parse_error", str(e)))
            continue

        file_dir = f.parent
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.level and node.module is not None:
                base = file_dir
                # In Python: level=1 means "from .foo" (same package), level=2 means "from ..foo" (parent), etc.
                for _ in range(node.level - 1):
                    base = base.parent
                target = base.joinpath(*node.module.split("."))
                file_candidate = target.with_suffix(".py")
                pkg_candidate = target / "__init__.py"
                if not file_candidate.exists() and not pkg_candidate.exists():
                    # case-insensitive suggestion
                    suggestions = []
                    parent = target.parent
                    leaf = target.name
                    if parent.exists():
                        for entry in parent.iterdir():
                            name = entry.name
                            if name.lower() in {leaf.lower(), (leaf + ".py").lower()}:
                                suggestions.append(name)
                    problems.append(
                        (rel, f"missing_relative_import: {'.' * node.level}{node.module}",
                         f"Expected {file_candidate.relative_to(repo_root)} or {pkg_candidate.relative_to(repo_root)}; suggestions: {suggestions}")
                    )
    return problems

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

    # Additional checks that catch common release issues
    init_warn = check_missing_init_files(PROJECT_ROOT)
    if init_warn:
        print("\n⚠️ Possible misnamed __init__.py files (found _init_.py without __init__.py):")
        for x in init_warn:
            print(" -", x)
    else:
        print("\n✅ Package __init__.py naming: OK")

    rel_import_issues = check_relative_imports(py_files, PROJECT_ROOT)
    if rel_import_issues:
        print("\n⚠️ Broken relative imports detected (may break on Linux/macOS):")
        for f, kind, detail in rel_import_issues[:50]:
            print(f" - {f} -> {kind}: {detail}")
        if len(rel_import_issues) > 50:
            print(f"   ... and {len(rel_import_issues) - 50} more")
    else:
        print("\n✅ Relative imports: OK")

    graph = build_import_graph(py_files)
    # quick: show top-level modules count
    print("\n📦 Python modules scanned:", len(graph))

    print("\nDone.")
    return 0 if (not missing and not syn) else 2

if __name__ == "__main__":
    raise SystemExit(main())
