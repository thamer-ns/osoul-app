"""Repository-wide static audit used by CI before merging to main."""
from __future__ import annotations

import ast
import hashlib
import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / "repository-audit.json"
EXCLUDED_DIRS = {
    ".git",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}
TEXT_SUFFIXES = {
    ".py",
    ".toml",
    ".yml",
    ".yaml",
    ".json",
    ".md",
    ".txt",
    ".ini",
    ".cfg",
    ".env",
    ".html",
    ".css",
    ".js",
    ".ts",
    ".sql",
}
SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[=:]\s*['\"]([^'\"]{12,})['\"]"),
    re.compile(r"postgres(?:ql)?://[^\s:'\"]+:[^\s@'\"]+@", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
]
PLACEHOLDER_WORDS = {
    "changeme",
    "example",
    "your_key_here",
    "your-secret-here",
    "replace_me",
    "put_a_strong_secret_here",
    "your_api_key",
    "user:password@host",
}


@dataclass
class Finding:
    severity: str
    path: str
    line: int
    code: str
    message: str


class PythonVisitor(ast.NodeVisitor):
    def __init__(self, path: Path, findings: list[Finding]):
        self.path = path
        self.findings = findings

    def add(self, node: ast.AST, severity: str, code: str, message: str) -> None:
        self.findings.append(
            Finding(
                severity=severity,
                path=str(self.path.relative_to(ROOT)),
                line=int(getattr(node, "lineno", 1) or 1),
                code=code,
                message=message,
            )
        )

    @staticmethod
    def _call_name(node: ast.Call) -> str:
        target = node.func
        if isinstance(target, ast.Name):
            return target.id
        if isinstance(target, ast.Attribute):
            parts = [target.attr]
            value = target.value
            while isinstance(value, ast.Attribute):
                parts.append(value.attr)
                value = value.value
            if isinstance(value, ast.Name):
                parts.append(value.id)
            return ".".join(reversed(parts))
        return ""

    @staticmethod
    def _is_true(node: ast.AST | None) -> bool:
        return isinstance(node, ast.Constant) and node.value is True

    @staticmethod
    def _is_false(node: ast.AST | None) -> bool:
        return isinstance(node, ast.Constant) and node.value is False

    def visit_Call(self, node: ast.Call) -> None:
        name = self._call_name(node)
        if name in {"eval", "exec"}:
            self.add(node, "critical", "PY_EXEC", f"Dynamic execution via {name}()")
        if name == "os.system":
            self.add(node, "critical", "OS_SYSTEM", "Shell execution via os.system()")
        if name.startswith("subprocess."):
            shell_kw = next((kw.value for kw in node.keywords if kw.arg == "shell"), None)
            if self._is_true(shell_kw):
                self.add(node, "critical", "SUBPROCESS_SHELL", "subprocess call uses shell=True")
        if name in {"pickle.load", "pickle.loads"}:
            self.add(node, "critical", "PICKLE_LOAD", "Unsafe pickle deserialization")
        if name == "yaml.load":
            has_safe_loader = any(
                kw.arg == "Loader"
                and isinstance(kw.value, ast.Attribute)
                and kw.value.attr in {"SafeLoader", "CSafeLoader"}
                for kw in node.keywords
            )
            if not has_safe_loader:
                self.add(node, "critical", "YAML_LOAD", "yaml.load without SafeLoader")
        if name.startswith("requests."):
            verify_kw = next((kw.value for kw in node.keywords if kw.arg == "verify"), None)
            if self._is_false(verify_kw):
                self.add(node, "critical", "TLS_VERIFY", "HTTP request disables TLS verification")
        if name in {"st.error", "st.warning", "st.info", "st.code", "streamlit.error", "streamlit.code"}:
            if node.args:
                arg = node.args[0]
                raw_exception = (
                    isinstance(arg, ast.Call)
                    and isinstance(arg.func, ast.Name)
                    and arg.func.id == "str"
                    and arg.args
                    and isinstance(arg.args[0], ast.Name)
                    and arg.args[0].id in {"e", "exc", "error", "exception"}
                )
                traceback_call = isinstance(arg, ast.Call) and "traceback" in self._call_name(arg)
                if raw_exception or traceback_call:
                    self.add(node, "critical", "ERROR_DISCLOSURE", "Raw exception details rendered to the UI")
        if name in {"st.markdown", "streamlit.markdown"}:
            unsafe = next((kw.value for kw in node.keywords if kw.arg == "unsafe_allow_html"), None)
            if self._is_true(unsafe) and node.args and isinstance(node.args[0], (ast.JoinedStr, ast.BinOp)):
                source_lines = self.path.read_text(encoding="utf-8").splitlines()
                start = max(0, int(getattr(node, "lineno", 1)) - 3)
                reviewed = any("audit: safe-dynamic-html" in line for line in source_lines[start : int(getattr(node, "lineno", 1))])
                if not reviewed:
                    self.add(node, "warning", "DYNAMIC_HTML", "Dynamic content rendered with unsafe_allow_html=True")
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if len(node.body) == 1 and isinstance(node.body[0], ast.Pass):
            self.add(node, "warning", "SILENT_EXCEPTION", "Exception is silently ignored")
        self.generic_visit(node)


def _iter_files():
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        if any(part in EXCLUDED_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_SUFFIXES or path.name in {
        "Dockerfile",
        "Procfile",
        ".gitignore",
        ".env.example",
    }


def _scan_secrets(path: Path, text: str, findings: list[Finding]) -> None:
    rel = str(path.relative_to(ROOT))
    if rel.endswith((".example", ".example.toml")) or path.name == ".env.example":
        return
    for line_number, line in enumerate(text.splitlines(), start=1):
        if line.lstrip().startswith("#"):
            continue
        if "re.compile(" in line or "SECRET_PATTERNS" in line:
            continue
        for pattern in SECRET_PATTERNS:
            match = pattern.search(line)
            if not match:
                continue
            lowered = line.lower()
            if any(word in lowered for word in PLACEHOLDER_WORDS):
                continue
            findings.append(
                Finding(
                    severity="critical",
                    path=rel,
                    line=line_number,
                    code="SECRET_LITERAL",
                    message="Potential hard-coded credential or connection secret",
                )
            )


def main() -> int:
    findings: list[Finding] = []
    manifest: list[dict] = []
    python_files = 0
    total_lines = 0

    for path in sorted(_iter_files()):
        rel = str(path.relative_to(ROOT))
        raw = path.read_bytes()
        entry = {
            "path": rel,
            "bytes": len(raw),
            "sha256": hashlib.sha256(raw).hexdigest(),
            "lines": None,
        }
        if _is_text_file(path):
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                findings.append(Finding("warning", rel, 1, "ENCODING", "Text file is not UTF-8"))
                manifest.append(entry)
                continue
            lines = text.count("\n") + (1 if text else 0)
            entry["lines"] = lines
            total_lines += lines
            _scan_secrets(path, text, findings)
            if path.suffix.lower() == ".py":
                python_files += 1
                try:
                    tree = ast.parse(text, filename=rel)
                except SyntaxError as exc:
                    findings.append(
                        Finding("critical", rel, int(exc.lineno or 1), "SYNTAX", str(exc.msg))
                    )
                else:
                    PythonVisitor(path, findings).visit(tree)
        manifest.append(entry)

    report = {
        "summary": {
            "files": len(manifest),
            "python_files": python_files,
            "text_lines": total_lines,
            "critical": sum(item.severity == "critical" for item in findings),
            "warnings": sum(item.severity == "warning" for item in findings),
        },
        "findings": [asdict(item) for item in findings],
        "manifest": manifest,
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    for finding in findings:
        print(
            f"::{ 'error' if finding.severity == 'critical' else 'warning' } "
            f"file={finding.path},line={finding.line},title={finding.code}::{finding.message}"
        )
    return 1 if report["summary"]["critical"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
