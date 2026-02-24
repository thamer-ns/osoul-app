# financial_analysis/parsers.py
import io
import re
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

import pandas as pd

from market_data import get_ticker_symbol
from .utils import _is_year_like, _fetch_html, BeautifulSoup

logger = logging.getLogger(__name__)

# PDF (اختياري)
try:
    import pdfplumber
except Exception:
    pdfplumber = None


class FinancialParser:
    """
    Parser مرن لالتقاط أهم البنود المالية من:
    - نصوص إعلانات (مثل تداول)
    - ملفات PDF (نصية)
    - Excel/CSV (بما فيها تصدير XBRL/القوائم)
    - Copy/Paste عربي/إنجليزي

    المخرجات:
    [
      {
        "date": "YYYY-MM-DD",
        "period_type": "Annual|Quarterly",
        "data": {...},
        "meta": {...}
      }
    ]
    """

    def __init__(self):
        self.mapping = {
            "revenue": [
                r"المبيعات\s*/?\s*الايرادات",
                r"المبيعات\s*/?\s*الإيرادات",
                r"(?:إجمالي\s*)?(?:الإيرادات|الايرادات)\b",
                r"\btotal\s+revenue\b",
                r"\brevenues?\b",
                r"\brevenue\b",
                r"\bsales\b",
            ],
            "gross_profit": [
                r"إجمالي\s*الربح(?:\s*\(الخسارة\))?",
                r"\bgross\s+profit\b",
            ],
            "operating_income": [
                r"الربح\s*\(الخسارة\)\s*التشغيلي",
                r"ربح\s*\(خسارة\)\s*العمليات",
                r"الربح\s*التشغيلي",
                r"\boperating\s+income\b",
                r"\boperating\s+profit\b",
                r"\bEBIT\b",
            ],
            "ebitda": [
                r"\bEBITDA\b",
                r"الأرباح\s*قبل\s*خصم\s*الفوائد.*EBITDA",
            ],
            "net_income": [
                r"صافي\s*الربح(?:\s*\(الخسارة\))?\s*العائد\s*لمساهمي\s*المصدر",
                r"صافي\s*الربح(?:\s*\(الخسارة\))?\s*العائد\s*لمساهمي",
                r"صافي\s*(?:الدخل|الربح)",
                r"الربح\s*\(الخسارة\)\s*للفترة",
                r"\bnet\s+income\b",
                r"\bnet\s+profit\b",
            ],
            "eps": [
                r"ربحية\s*\(خسارة\)\s*السهم",
                r"ربح\s*السهم",
                r"\beps\b",
                r"earnings\s+per\s+share",
            ],
            "total_assets": [
                r"إجمالي\s*(?:الموجودات|الأصول)",
                r"\btotal\s+assets\b",
            ],
            "current_assets": [
                r"(?:إجمالي\s*)?الموجودات\s*المتداولة",
                r"\bcurrent\s+assets\b",
            ],
            "total_liabilities": [
                r"إجمالي\s*(?:المطلوبات|الالتزامات)",
                r"\btotal\s+liabilities\b",
            ],
            "current_liabilities": [
                r"(?:إجمالي\s*)?المطلوبات\s*المتداولة",
                r"\bcurrent\s+liabilities\b",
            ],
            "total_equity": [
                r"إجمالي\s*حقوق\s*الملكية",
                r"حقوق\s*الملكية\s*المتعلقة\s*بملاك\s*الشركة\s*الأم",
                r"\btotal\s+equity\b",
                r"\bshareholders?\s+equity\b",
            ],
            "long_term_debt": [
                r"سندات\s*دين\s*وقروض\s*لأجل.*صكوك",
                r"قروض\s*طويلة\s*الأجل",
                r"\blong\s*term\s*debt\b",
                r"\bnon[-\s]?current\s+debt\b",
            ],
            "interest_expense": [
                r"تكلفة\s*تمويل",
                r"مصروف(?:ات)?\s*تمويل",
                r"\bfinance\s+costs?\b",
                r"\binterest\s+expense\b",
            ],
            "operating_cash_flow": [
                r"صافي\s*التدفقات\s*النقدية\s*من\s*\(?[^\n]*النشاطات\s*التشغيلية",
                r"صافي\s*التدفقات\s*النقدية\s*من\s*\(?[^\n]*العمليات",
                r"\boperating\s+cash\s+flow\b",
                r"cash\s+from\s+operat",
            ],
            "investing_cash_flow": [
                r"صافي\s*التدفقات\s*النقدية\s*من\s*\(?[^\n]*النشاطات\s*الاستثمارية",
                r"\binvesting\s+cash\s+flow\b",
                r"cash\s+from\s+invest",
            ],
            "financing_cash_flow": [
                r"صافي\s*التدفقات\s*النقدية\s*من\s*\(?[^\n]*النشاطات\s*التمويلية",
                r"\bfinancing\s+cash\s+flow\b",
                r"cash\s+from\s+financ",
            ],
            "shares_outstanding": [
                r"المتوسط\s*المرجح\s*لعدد\s*الأسهم\s*القائمة",
                r"المتوسط\s*المرجح\s*لعدد\s*الأسهم(?:\s*العادية)?\s*(?:القائمة|المتداولة)?",
                r"weighted\s+average\s+number\s+of\s+shares",
                r"shares\s+outstanding",
            ],
        }
        self._compiled = {
            k: [re.compile(p, flags=re.IGNORECASE) for p in pats]
            for k, pats in self.mapping.items()
        }
        self._global_multiplier = 1.0

    @staticmethod
    def _normalize_digits(s: str) -> str:
        if s is None:
            return ""
        trans = str.maketrans("٠١٢٣٤٥٦٧٨٩٫٬", "0123456789.,")
        return str(s).translate(trans)

    @staticmethod
    def _normalize_text(s: str) -> str:
        s = FinancialParser._normalize_digits(str(s or ""))
        s = s.replace("\u200f", " ").replace("\u200e", " ").replace("\ufeff", " ")
        s = s.replace("ـ", "")
        s = s.replace("\xa0", " ")
        s = re.sub(r"[ \t]+", " ", s)
        return s.strip()

    @staticmethod
    def _safe_float(x):
        try:
            return float(x)
        except Exception:
            return None

    def _detect_unit_multiplier(self, text: str) -> float:
        t = self._normalize_text(text).lower()
        if "بالآلاف" in t or "بالالاف" in t or "بالألف" in t or "بالالف" in t:
            return 1_000.0
        if "بالملايين" in t or "بالمليون" in t or "جميع الأرقام بالـ (مليون)" in t:
            return 1_000_000.0
        if "بالمليارات" in t or "بالمليار" in t:
            return 1_000_000_000.0
        if "مستوى التقريب المستخدم" in t and "بالآلاف" in t:
            return 1_000.0
        if "in thousands" in t or "thousands" in t:
            return 1_000.0
        if "in millions" in t or "millions" in t:
            return 1_000_000.0
        if "in billions" in t or "billions" in t:
            return 1_000_000_000.0
        return 1.0

    def _clean_number(self, val_str, global_multiplier: float = 1.0):
        if pd.isna(val_str):
            return 0.0
        s = self._normalize_digits(str(val_str)).strip().upper()
        if not s:
            return 0.0
        multiplier = 1.0
        gm = float(global_multiplier or 1.0)
        if gm <= 0:
            gm = 1.0

        if s.endswith("B") or "مليار" in s:
            multiplier = 1_000_000_000.0
        elif s.endswith("M") or "مليون" in s:
            multiplier = 1_000_000.0
        elif s.endswith("K") or "ألف" in s or "الاف" in s:
            multiplier = 1_000.0
        elif gm != 1.0:
            multiplier = gm

        neg = "(" in s and ")" in s
        s = re.sub(r"[^\d\.\-]", "", s)
        if not s:
            return 0.0
        if neg and not s.startswith("-"):
            s = "-" + s
        try:
            return float(s) * multiplier
        except Exception:
            return 0.0

    def _extract_symbol(self, text: str) -> Optional[str]:
        txt = self._normalize_text(text)
        candidates = re.findall(r"\b([1-9]\d{3,4})\b", txt)
        for m in candidates:
            if m.startswith("20") and len(m) == 4:
                continue
            return f"{m}.SR"
        return None

    def _extract_dates(self, text: str) -> List[str]:
        t = self._normalize_text(text)
        dates = set(re.findall(r"\b(20\d{2}-\d{2}-\d{2})\b", t))
        for d, m, y in re.findall(r"\b(\d{2})[/-](\d{2})[/-](20\d{2})\b", t):
            try:
                dates.add(f"{int(y):04d}-{int(m):02d}-{int(d):02d}")
            except Exception:
                pass
        out = []
        for ds in dates:
            try:
                datetime.strptime(ds, "%Y-%m-%d")
                out.append(ds)
            except Exception:
                continue
        return sorted(set(out))

    def _best_statement_date(self, text: str, dates: List[str]) -> str:
        if not dates:
            return datetime.now().strftime("%Y-%m-%d")
        t = self._normalize_text(text)
        m = re.search(r"(?:نهاية\s*الفترة|الفترة\s*المنتهية\s*في|for\s*the\s*period\s*ended)\s*[:\-]?\s*(20\d{2}-\d{2}-\d{2})", t, flags=re.I)
        if m:
            return m.group(1)
        return sorted(dates)[-1]

    def _infer_period_type(self, text: str) -> str:
        t = self._normalize_text(text).lower()
        if any(k in t for k in ["النتائج المالية الموحدة السنوية", "السنة الحالية", "السنة الماضية", "سنوية", "annual"]):
            return "Annual"
        if any(k in t for k in ["الربع", "ربع", "التسعة أشهر", "تسعة أشهر", "الثلاثة أشهر", "ثلاثة أشهر", "quarter", "interim"]):
            return "Quarterly"
        return "Annual"

    def _extract_numbers_from_line(self, line: str) -> List[float]:
        tokens = re.findall(r"(\(?-?\d[\d,]*\.?\d*\)?)", self._normalize_digits(line))
        vals: List[float] = []
        for tok in tokens:
            if re.fullmatch(r"20\d{2}", tok) and ("-" in line or "/" in line):
                continue
            vals.append(self._clean_number(tok, self._global_multiplier))
        return vals

    def _extract_metrics_from_lines(self, lines: List[str]) -> Dict[str, float]:
        extracted: Dict[str, float] = {}
        line_scores: Dict[str, int] = {}

        for raw_line in lines:
            line = self._normalize_text(raw_line)
            if not line:
                continue
            compact = line.replace(" ", "")
            variants = [line] + ([compact] if compact != line else [])

            for key, patterns in self._compiled.items():
                matched = False
                for v in variants:
                    if any(p.search(v) for p in patterns):
                        nums = self._extract_numbers_from_line(line)
                        if not nums:
                            break
                        val = nums[0]
                        score = 0
                        score += 3 if len(nums) >= 2 else 0
                        score += 2 if any(ch in line for ch in ["إجمالي", "صافي", "total", "net"]) else 0
                        score += 1 if ("\t" in raw_line or "," in line) else 0
                        prev_score = line_scores.get(key, -1)
                        if key not in extracted or score >= prev_score:
                            # EPS يجب عدم ضربها بمقياس الوحدة العام
                            if key == "eps":
                                val = self._clean_number(str(nums[0]), 1.0)
                            extracted[key] = float(val)
                            line_scores[key] = score
                        matched = True
                        break
                if matched:
                    break

        if "total_equity" not in extracted and "total_assets" in extracted and "total_liabilities" in extracted:
            extracted["total_equity"] = extracted["total_assets"] - extracted["total_liabilities"]
        return extracted

    def _rows_to_text_lines(self, df: pd.DataFrame) -> List[str]:
        lines: List[str] = []
        try:
            df = df.fillna("")
        except Exception:
            pass
        for _, row in df.iterrows():
            vals = []
            for x in row.tolist():
                s = self._normalize_text(x)
                if not s or s.lower() == "nan":
                    continue
                vals.append(s)
            if vals:
                lines.append("\t".join(vals))
        return lines


    def _to_bytes_io(self, uploaded_file):
        name = getattr(uploaded_file, "name", "upload") or "upload"
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        raw = uploaded_file.read()
        if isinstance(raw, str):
            raw = raw.encode("utf-8", errors="ignore")
        bio = io.BytesIO(raw or b"")
        bio.name = name
        bio.seek(0)
        return bio

    def _read_excel_workbook_to_text(self, uploaded_file) -> Tuple[str, Optional[str]]:
        name = (getattr(uploaded_file, "name", "") or "").lower()
        bio = self._to_bytes_io(uploaded_file)
        try:
            xls = pd.ExcelFile(bio)
        except ImportError as e:
            if name.endswith(".xls"):
                return "", "ملف .xls يحتاج مكتبة xlrd. أضفها إلى requirements.txt ثم أعد التشغيل."
            return "", f"تعذر قراءة ملف Excel: {e}"
        except Exception as e:
            return "", f"تعذر قراءة ملف Excel: {e}"

        all_lines: List[str] = []
        for sheet in xls.sheet_names:
            try:
                df = xls.parse(sheet_name=sheet, header=None, dtype=str)
            except Exception as e:
                logger.warning("تعذر قراءة الشيت %s: %s", sheet, e)
                continue
            all_lines.append(f"[SHEET] {sheet}")
            all_lines.extend(self._rows_to_text_lines(df))
        return "\n".join(all_lines), None

    def _read_csv_to_text(self, uploaded_file) -> Tuple[str, Optional[str]]:
        try:
            uploaded_file.seek(0)
        except Exception:
            pass
        for enc in ("utf-8", "utf-8-sig", "cp1256", "latin1"):
            try:
                bio = self._to_bytes_io(uploaded_file)
                df = pd.read_csv(bio, header=None, dtype=str, encoding=enc)
                return "\n".join(self._rows_to_text_lines(df)), None
            except Exception:
                try:
                    uploaded_file.seek(0)
                except Exception:
                    pass
                continue
        return "", "تعذر قراءة CSV."

    def _read_pdf_to_text(self, uploaded_file) -> Tuple[str, Optional[str]]:
        if not pdfplumber:
            return "", "مكتبة pdfplumber غير مثبتة."
        bio = self._to_bytes_io(uploaded_file)
        parts: List[str] = []
        try:
            with pdfplumber.open(bio) as pdf:
                for i, page in enumerate(pdf.pages, start=1):
                    txt = page.extract_text() or ""
                    if txt:
                        parts.append(f"[PAGE {i}]")
                        parts.append(txt)
            if not parts:
                return "", "تعذر استخراج نص من PDF (قد يكون صورة ممسوحة)."
            return "\n".join(parts), None
        except Exception as e:
            return "", f"خطأ في قراءة PDF: {e}"

    def _detect_format_and_parse(self, text: str):
        text = text or ""
        self._global_multiplier = self._detect_unit_multiplier(text)
        lines = [ln for ln in text.split("\n") if self._normalize_text(ln)]

        symbol = self._extract_symbol(text)
        statement_date = self._best_statement_date(text, self._extract_dates(text))
        period_type = self._infer_period_type(text)

        data = self._extract_metrics_from_lines(lines)
        if len(data) < 3:
            compact_lines = []
            for ln in lines:
                n = self._normalize_text(ln)
                compact_lines.append(n)
                compact_lines.append(n.replace(" ", ""))
            data2 = self._extract_metrics_from_lines(compact_lines)
            if len(data2) > len(data):
                data = data2

        if not data:
            return [], symbol

        rec = {
            "date": statement_date,
            "period_type": period_type,
            "data": data,
            "meta": {
                "detected_unit_multiplier": self._global_multiplier,
                "source_format": "text",
                "parse_confidence": min(0.95, 0.25 + 0.08 * len(data)),
            },
        }
        return [rec], symbol

    def process_file_or_text(self, uploaded_file=None, text_input=None):
        text = ""
        if text_input:
            text = str(text_input)
        elif uploaded_file:
            filename = (uploaded_file.name or "").lower()
            try:
                if filename.endswith(".pdf"):
                    text, err = self._read_pdf_to_text(uploaded_file)
                elif filename.endswith((".xlsx", ".xls")):
                    text, err = self._read_excel_workbook_to_text(uploaded_file)
                elif filename.endswith(".csv"):
                    text, err = self._read_csv_to_text(uploaded_file)
                elif filename.endswith((".txt", ".md")):
                    try:
                        uploaded_file.seek(0)
                    except Exception:
                        pass
                    raw = uploaded_file.read()
                    if isinstance(raw, bytes):
                        text = raw.decode("utf-8", errors="ignore")
                    else:
                        text = str(raw or "")
                    err = None
                else:
                    return [], None, "صيغة الملف غير مدعومة (PDF/XLS/XLSX/CSV/TXT)."
            except Exception as e:
                logger.exception("خطأ أثناء قراءة الملف المالي")
                return [], None, f"خطأ في قراءة الملف: {e}"

            if err:
                return [], None, err

        if not text.strip():
            return [], None, "لا يوجد نص للمعالجة"

        results, symbol = self._detect_format_and_parse(text)
        if not results:
            return [], symbol, "تعذر استخراج البنود المالية الأساسية من النص/الملف. جرّب ملفًا أوضح أو ألصق الجدول مباشرة."
        return results, symbol, None


# ==============================================================
# 🌍 External Sources (best-effort, safe)
# ==============================================================
def fetch_financials_from_google_finance(symbol: str) -> dict:
    try:
        sym = get_ticker_symbol(symbol).replace(".SR", "")
        if not sym.isdigit():
            return {}
        url = f"https://www.google.com/finance/quote/{sym}:TADAWUL"
        html = _fetch_html(url, timeout=7)
        if not html:
            return {}
        soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
        txt = soup.get_text("\n", strip=True) if soup else ""
        if not txt.strip():
            return {}
        parser = FinancialParser()
        results, _ = parser._detect_format_and_parse(txt)
        if not results:
            return {}
        rec = sorted(results, key=lambda x: x.get("date", ""), reverse=True)[0]
        data = rec.get("data", {}) or {}
        data["date"] = rec.get("date")
        data["_source_url"] = url
        return data
    except Exception:
        return {}


def fetch_financials_from_argaam(symbol: str) -> dict:
    s = get_ticker_symbol(symbol).replace(".SR", "")
    if not s.isdigit():
        return {}
    urls = [
        f"https://www.argaam.com/en/company/financials/{s}",
        f"https://www.argaam.com/ar/company/financials/{s}",
        f"https://www.argaam.com/en/company/stock/overview/{s}",
        f"https://www.argaam.com/ar/company/stock/overview/{s}",
    ]
    for url in urls:
        try:
            html = _fetch_html(url, timeout=8)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser") if BeautifulSoup else None
            txt = soup.get_text("\n", strip=True) if soup else ""
            if not txt.strip():
                continue
            parser = FinancialParser()
            results, _ = parser._detect_format_and_parse(txt)
            if not results:
                continue
            rec = sorted(results, key=lambda x: x.get("date", ""), reverse=True)[0]
            data = rec.get("data", {}) or {}
            data["date"] = rec.get("date")
            data["_source_url"] = url
            return data
        except Exception:
            continue
    return {}
