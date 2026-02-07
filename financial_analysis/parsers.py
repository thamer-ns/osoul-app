# financial_analysis/parsers.py
import io
import re
from datetime import datetime
from typing import Dict, List, Any, Tuple, Optional

import pandas as pd

from market_data import get_ticker_symbol
from .utils import _is_year_like, _fetch_html, BeautifulSoup

# PDF (اختياري)
try:
    import pdfplumber
except Exception:
    pdfplumber = None


# ==============================================================
# 🧠 FinancialParser
# ==============================================================
class FinancialParser:
    """
    - يدعم PDF تداول
    - يدعم Excel/CSV نصي
    - يدعم Copy/Paste من المتصفح (TradingView / أرقام / Investing / Google Finance)
    """

    def __init__(self):
        self.mapping = {
            "revenue": [
                r"إجمالي\s*الإيرادات",
                r"\bالمبيعات\b",
                r"\bsales\b",
                r"\btotal\s+revenue\b",
                r"\brevenues?\b",
                r"\brevenue\b",
            ],
            "net_income": [
                r"صافي\s*(الدخل|الربح)",
                r"\bnet\s+income\b",
                r"\bnet\s+profit\b",
                r"الربح\s*\(الخسارة\)\s*للفترة",
                r"صافي\s*الدخل\s*العائد",
            ],
            "total_assets": [
                r"إجمالي\s*(الموجودات|الأصول)",
                r"\btotal\s+assets\b",
                r"\bassets\b",
            ],
            "total_liabilities": [
                r"إجمالي\s*(المطلوبات|الالتزامات)",
                r"\btotal\s+liabilities\b",
                r"\bliabilities\b",
            ],
            "total_equity": [
                r"إجمالي\s*حقوق\s*الملكية",
                r"حقوق\s*(المساهمين|الملّاك)",
                r"\btotal\s+equity\b",
                r"\bshareholders?\s+equity\b",
            ],
            "operating_cash_flow": [
                r"صافي\s*التدفقات\s*النقدية\s*من\s*.*التشغيلية",
                r"\boperating\s+cash\s+flow\b",
                r"\bcash\s+from\s+operating\b",
                r"التدفقات\s*النقدية\s*التشغيلية",
                r"نقد\s*من\s*العمليات",
            ],
            "current_assets": [
                r"(إجمالي\s*)?الموجودات\s*المتداولة",
                r"\bcurrent\s+assets\b",
            ],
            "current_liabilities": [
                r"(إجمالي\s*)?المطلوبات\s*المتداولة",
                r"\bcurrent\s+liabilities\b",
            ],
            "long_term_debt": [
                r"قروض\s*طويلة\s*الأجل",
                r"\blong\s+term\s+debt\b",
                r"مطلوبات\s*غير\s*متداولة",
                r"\bnon[-\s]?current\s+liabilities\b",
            ],
        }

        self._compiled = {k: [re.compile(p, flags=re.IGNORECASE) for p in pats] for k, pats in self.mapping.items()}

    def _clean_number(self, val_str):
        if pd.isna(val_str):
            return 0.0

        s = str(val_str).strip().upper()

        arabic_digits = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
        s = s.translate(arabic_digits)

        multiplier = 1.0
        if s.endswith("B") or "مليار" in s:
            multiplier = 1_000_000_000
        elif s.endswith("M") or "مليون" in s:
            multiplier = 1_000_000
        elif s.endswith("K") or "ألف" in s:
            multiplier = 1_000

        s = re.sub(r"[^\d\.\-\(\)]", "", s)

        if "(" in s and ")" in s:
            s = s.replace("(", "-").replace(")", "")

        try:
            return float(s) * multiplier
        except Exception:
            return 0.0

    def _extract_symbol(self, text):
        txt = str(text or "")
        matches = re.findall(r"\b([1-9]\d{3})\b", txt)
        for m in matches:
            if not m.startswith("20"):
                return f"{m}.SR"
        return None

    def _detect_format_and_parse(self, text):
        lines = (text or "").split("\n")

        if any(re.search(r"\[\d{6}\]", line) for line in lines):
            return self._parse_tadawul_style(lines)

        return self._parse_table_style(lines)

    def _parse_tadawul_style(self, lines):
        extracted_data = {}
        dates = []
        symbol = None

        for line in lines:
            if not symbol:
                symbol = self._extract_symbol(line)

            dm = re.findall(r"(\d{4}-\d{2}-\d{2})", line)
            if dm and not dates:
                dates = sorted(list(set(dm)), reverse=True)[:4]

        if not dates:
            for line in lines:
                years = re.findall(r"\b(20\d{2})\b", line)
                years = [y for y in years if _is_year_like(y)]
                if len(set(years)) >= 2:
                    dates = [f"{y}-12-31" for y in sorted(list(set(years)), reverse=True)[:4]]
                    break

        if not dates:
            dates = [datetime.now().strftime("%Y-12-31")]

        for line in lines:
            line = (line or "").strip()
            if not line:
                continue

            for key, patterns in self._compiled.items():
                if any(p.search(line) for p in patterns):
                    nums = re.findall(r"(\(?-?[\d,]{2,}(?:\.\d+)?\)?)", line)
                    if not nums:
                        continue

                    clean_nums = [self._clean_number(n) for n in nums]

                    for i, d in enumerate(dates):
                        if i < len(clean_nums):
                            extracted_data.setdefault(d, {})
                            prev = extracted_data[d].get(key, 0.0)
                            if abs(clean_nums[i]) > abs(prev):
                                extracted_data[d][key] = clean_nums[i]
                    break

        results = [{"date": d, "data": data} for d, data in extracted_data.items()]
        return results, symbol

    def _parse_table_style(self, lines):
        try:
            raw = "\n".join([str(x) for x in lines if str(x).strip()])
            if not raw.strip():
                return [], None

            clean_text = "\n".join([re.sub(r" {2,}|\t", ",", ln) for ln in raw.split("\n")])
            df = pd.read_csv(io.StringIO(clean_text), header=None, on_bad_lines="skip")

            date_row_idx = -1
            dates = []
            for idx, row in df.iterrows():
                row_vals = [str(x) for x in row.values if str(x).strip() != "nan"]
                row_str = " ".join(row_vals)

                years = re.findall(r"\b(20\d{2})\b", row_str)
                years = [y for y in years if _is_year_like(y)]
                if len(set(years)) >= 2:
                    date_row_idx = idx
                    for col_idx, val in enumerate(row.values):
                        s = str(val)
                        m = re.search(r"\b(20\d{2})\b", s)
                        if m:
                            dates.append((col_idx, f"{m.group(1)}-12-31"))
                    break

                if re.search(r"\d{4}-\d{2}-\d{2}", row_str):
                    date_row_idx = idx
                    for col_idx, val in enumerate(row.values):
                        s = str(val)
                        m = re.search(r"(\d{4}-\d{2}-\d{2})", s)
                        if m:
                            dates.append((col_idx, m.group(1)))
                    break

            if date_row_idx == -1 or not dates:
                return [], self._extract_symbol("\n".join(lines[:10]))

            results_map = {}

            for idx, row in df.iterrows():
                if idx <= date_row_idx:
                    continue
                label = str(row.iloc[0]) if len(row) else ""
                if not label or label == "nan":
                    continue

                for key, patterns in self._compiled.items():
                    if any(p.search(label) for p in patterns):
                        for col_idx, d in dates:
                            if col_idx < len(row):
                                v = self._clean_number(row.iloc[col_idx])
                                results_map.setdefault(d, {})
                                results_map[d][key] = v
                        break

            final_res = [{"date": d, "data": data} for d, data in results_map.items()]
            symbol = self._extract_symbol("\n".join(lines[:10]))
            return final_res, symbol

        except Exception as e:
            print(f"Parsing Error: {e}")
            return [], None

    def process_file_or_text(self, uploaded_file=None, text_input=None):
        text = ""

        if text_input:
            text = text_input

        elif uploaded_file:
            filename = (uploaded_file.name or "").lower()
            try:
                if filename.endswith(".pdf"):
                    if not pdfplumber:
                        return [], None, "مكتبة pdfplumber غير مثبتة."
                    with pdfplumber.open(uploaded_file) as pdf:
                        for page in pdf.pages:
                            t = page.extract_text() or ""
                            text += t + "\n"

                elif filename.endswith((".xlsx", ".xls")):
                    df = pd.read_excel(uploaded_file)
                    text = df.to_string(index=False)

                elif filename.endswith(".csv"):
                    df = pd.read_csv(uploaded_file)
                    text = df.to_string(index=False)

                else:
                    return [], None, "صيغة الملف غير مدعومة."

            except Exception as e:
                return [], None, f"خطأ في قراءة الملف: {e}"

        if not text.strip():
            return [], None, "لا يوجد نص للمعالجة"

        results, symbol = self._detect_format_and_parse(text)
        return results, symbol, None


# ==============================================================
# 🌍 External Sources (best-effort, safe)
# ==============================================================
def fetch_financials_from_google_finance(symbol: str) -> dict:
    """
    Best-effort parsing from Google Finance text -> FinancialParser.
    قد تتغير الصفحة لذلك نعتبره احتياطي فقط.
    """
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

        results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)
        rec = results[0]
        data = rec.get("data", {}) or {}
        data["date"] = rec.get("date")
        data["_source_url"] = url
        return data
    except Exception:
        return {}


def fetch_financials_from_argaam(symbol: str) -> dict:
    """
    Best-effort parsing from Argaam text -> FinancialParser.
    قد تتغير الصفحة لذلك نعتبره احتياطي فقط.
    """
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

            results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)
            rec = results[0]
            data = rec.get("data", {}) or {}
            data["date"] = rec.get("date")
            data["_source_url"] = url
            return data
        except Exception:
            continue

    return {}


def fetch_financials_from_tadawul(symbol: str) -> dict:
    """Best-effort snapshot from Tadawul (Saudi Exchange).

    الهدف هنا تقليل اعتمادنا على Yahoo عند تعذرها (429/Timeout) عبر
    محاولة استخراج أرقام أساسية من صفحة تداول إن توفرت.

    ⚠️ هذا مسار احتياطي فقط، وإذا تغيرت الصفحة/تعذر التحميل يعيد {}.
    """
    if not requests or not BeautifulSoup:
        return {}

    s = get_ticker_symbol(symbol).replace(".SR", "")
    if not s.isdigit():
        return {}

    # صفحات تداول تتغير، لذا نجرّب أكثر من نمط URL بشكل محافظ.
    urls = [
        f"https://www.saudiexchange.sa/wps/portal/tadawul/markets/equities/quote/{s}",
        f"https://www.saudiexchange.sa/wps/portal/tadawul/markets/quotedetails/quote/{s}",
    ]

    for url in urls:
        try:
            html = _fetch_html(url, timeout=8)
            if not html:
                continue
            soup = BeautifulSoup(html, "html.parser")
            txt = soup.get_text("\n", strip=True)
            if not txt:
                continue

            # نستخدم نفس FinancialParser الذي يستخدمه أرقام/قوقل
            parser = FinancialParser()
            results, _ = parser._detect_format_and_parse(txt)
            if not results:
                continue

            results = sorted(results, key=lambda x: x.get("date", ""), reverse=True)
            rec = results[0]
            data = rec.get("data", {}) or {}
            data["date"] = rec.get("date")
            data["_source_url"] = url
            data["source"] = "Tadawul"
            return data
        except Exception:
            continue

    return {}
