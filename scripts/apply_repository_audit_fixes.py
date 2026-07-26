"""One-time idempotent fixes produced by the repository-wide audit."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def write(path: str, content: str) -> None:
    (ROOT / path).write_text(content, encoding="utf-8")


def replace_required(path: str, old: str, new: str, *, count: int = 1) -> None:
    content = read(path)
    if old not in content:
        if new in content:
            print(f"already fixed: {path}")
            return
        raise RuntimeError(f"expected block not found in {path}")
    write(path, content.replace(old, new, count))
    print(f"fixed: {path}")


def fix_classical_analysis() -> None:
    path = "classical_analysis.py"
    content = read(path)
    if "def _os_card(" in content:
        return
    marker = "\n\ndef _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:\n"
    helper = '''\n\ndef _os_card(title: str, rows: list, icon: str = "") -> None:\n    """Render a compact native Streamlit card without unsafe dynamic HTML."""\n    with st.container(border=True):\n        heading = f"{icon} {title}".strip()\n        st.markdown(f"**{heading}**")\n        for label, value in rows:\n            st.write(f"**{label}:** {value}")\n\n\ndef _atr(df: pd.DataFrame, n: int = 14) -> pd.Series:\n'''
    if marker not in content:
        raise RuntimeError("classical analysis insertion marker missing")
    write(path, content.replace(marker, helper, 1))


def fix_market_data() -> None:
    path = "market_data.py"
    content = read(path)
    if "_LAST_LINEAGE:" not in content:
        marker = "import numpy as np\n\n"
        addition = '''import numpy as np\n\n_LAST_LINEAGE: Dict[str, Dict[str, Any]] = {}\n\n\ndef _sym_key(symbol: object) -> str:\n    return str(symbol or "").strip().upper()\n\n'''
        if marker not in content:
            raise RuntimeError("market_data imports marker missing")
        content = content.replace(marker, addition, 1)

    pattern = re.compile(
        r"def fetch_price_from_argaam\(symbol: str\) -> float:.*?"
        r"(?=\n# =+\n# 🟨 Yahoo Finance)",
        flags=re.DOTALL,
    )
    replacement = '''def fetch_price_from_argaam(symbol: str) -> float:\n    """Fetch a Saudi stock price from Argaam as a last-resort fallback."""\n    cleaned = _clean_symbol_text(str(symbol or "")).strip().upper()\n    if not cleaned:\n        return 0.0\n    code = cleaned.replace(".SR", "").replace("^", "")\n    if not code.isdigit():\n        return 0.0\n\n    url_candidates = [\n        f"https://www.argaam.com/ar/company/stock/overview/{code}",\n        f"https://www.argaam.com/en/company/stock/overview/{code}",\n        f"https://www.argaam.com/ar/company/stock/quote/{code}",\n    ]\n    for url in url_candidates:\n        response = _http_get(url, timeout=7, retries=1)\n        if response is None:\n            continue\n        price = _extract_argaam_price_from_html(response.text)\n        if _is_reasonable_price(price):\n            return float(price)\n    return 0.0\n\n\ndef fetch_argaam_snapshot(symbol: str) -> Dict[str, object]:\n    """Return a stable fallback snapshot without fabricating daily change."""\n    try:\n        price = float(fetch_price_from_argaam(symbol))\n    except Exception:\n        price = 0.0\n    return {\n        "symbol": str(symbol or ""),\n        "price": price,\n        "prev_close": None,\n        "change_pct": None,\n        "source": "argaam",\n    }\n\n'''
    content, replacements = pattern.subn(replacement, content, count=1)
    if replacements != 1 and "last-resort fallback" not in content:
        raise RuntimeError("Argaam function block not found")
    write(path, content)


def fix_logging() -> None:
    path = "osoli_logging.py"
    content = read(path)
    content = re.sub(
        r"\n(?P<indent>\s+)import logging\n(?P=indent)logging\.getLogger",
        lambda match: "\n" + match.group("indent") + "logging.getLogger",
        content,
    )
    write(path, content)


def fix_error_disclosures() -> None:
    replace_required(
        "views/analysis/financial.py",
        '''                except Exception as e:\n                    st.error(str(e))\n''',
        '''                except Exception:\n                    import logging\n\n                    logging.getLogger(__name__).exception(\n                        "Fundamental data-quality assessment failed"\n                    )\n                    st.error("تعذر فحص جودة البيانات المالية حاليًا.")\n''',
    )
    replace_required(
        "views/lab.py",
        '''        except Exception as e:\n            st.error(f"Backtest Error: {e}")\n            st.code(traceback.format_exc())\n''',
        '''        except Exception:\n            import logging\n\n            logging.getLogger(__name__).exception("Backtest execution failed")\n            st.error("تعذر تنفيذ الاختبار الخلفي. راجع البيانات والإعدادات ثم أعد المحاولة.")\n''',
    )
    replace_required(
        "views/shared.py",
        '''    except Exception as e:\n        st.warning("⚠️ تعذر عرض البطاقات المحسّنة، سيتم استخدام العرض الأصلي.")\n        st.code(str(e))\n''',
        '''    except Exception:\n        import logging\n\n        logging.getLogger(__name__).exception("Enhanced Osoli report rendering failed")\n        st.warning("⚠️ تعذر عرض البطاقات المحسّنة، سيتم استخدام العرض الأصلي.")\n''',
    )


def fix_requirements() -> None:
    path = "requirements.txt"
    content = read(path)
    content = re.sub(r"^lxml[^\n]*$", "lxml>=6.1.0,<7.0.0", content, flags=re.MULTILINE)
    content = re.sub(r"^pytest[^\n]*$", "pytest>=9.0.3,<10.0.0", content, flags=re.MULTILINE)
    write(path, content)


def fix_audit_false_positives() -> None:
    path = "tools/repository_audit.py"
    content = read(path)
    content = content.replace(
        '''    "replace_me",\n}\n''',
        '''    "replace_me",\n    "put_a_strong_secret_here",\n    "your_api_key",\n    "user:password@host",\n}\n''',
        1,
    )
    content = content.replace(
        '''    for line_number, line in enumerate(text.splitlines(), start=1):\n        for pattern in SECRET_PATTERNS:\n''',
        '''    for line_number, line in enumerate(text.splitlines(), start=1):\n        if "re.compile(" in line or "SECRET_PATTERNS" in line:\n            continue\n        for pattern in SECRET_PATTERNS:\n''',
        1,
    )
    write(path, content)


def fix_workflow_condition() -> None:
    path = ".github/workflows/quality-v2.yml"
    content = read(path)
    old = '''        if: >-\n          steps.ruff.outcome == 'failure' ||\n          steps.repository_audit.outcome == 'failure' ||\n          steps.bandit.outcome == 'failure' ||\n          steps.dependency_audit.outcome == 'failure'\n'''
    new = '''        if: ${{ steps.ruff.outcome == 'failure' || steps.repository_audit.outcome == 'failure' || steps.bandit.outcome == 'failure' || steps.dependency_audit.outcome == 'failure' }}\n'''
    if old in content:
        content = content.replace(old, new, 1)
    write(path, content)


def main() -> None:
    fix_classical_analysis()
    fix_market_data()
    fix_logging()
    fix_error_disclosures()
    fix_requirements()
    fix_audit_false_positives()
    fix_workflow_condition()
    print("repository audit fixes applied")


if __name__ == "__main__":
    main()
