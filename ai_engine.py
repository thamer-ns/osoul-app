# ai_engine.py
# ✅ AI Engine (Fail-safe + required API)
# Provides: generate(), self_test(), diagnose()
# هدفه: منع كسر صفحة المستشار + إعطاء نتيجة تحليل حتى لو بعض المحركات غير متوفرة

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple, List
import math

import pandas as pd
import numpy as np

# Optional imports (never crash if missing)
try:
    from market_data import get_ticker_symbol, get_chart_history, get_relative_strength_vs_tasi
except Exception:
    get_ticker_symbol = lambda x: str(x or "").strip()
    get_chart_history = None
    get_relative_strength_vs_tasi = None

try:
    from financial_analysis import (
        get_fundamental_ratios,
        get_financial_statements,
        get_thesis,
    )
except Exception:
    get_fundamental_ratios = None
    get_financial_statements = None
    get_thesis = None


# ============================================================
# 🧰 Helpers
# ============================================================

def _safe_float(x, default: float = 0.0) -> float:
    try:
        if x is None:
            return default
        if isinstance(x, (np.floating, np.integer)):
            return float(x)
        s = str(x).replace(",", "").strip()
        if s.lower() in ("nan", "none", ""):
            return default
        return float(s)
    except Exception:
        return default


def _pct(a, b, default=0.0) -> float:
    a = _safe_float(a, 0.0)
    b = _safe_float(b, 0.0)
    if b == 0:
        return default
    return (a - b) / b


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0)
    loss = (-delta).clip(lower=0)
    avg_gain = gain.ewm(alpha=1 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1 / period, adjust=False).mean()
    rs = avg_gain / (avg_loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    return rsi.fillna(0)


def _macd(close: pd.Series) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema12 = _ema(close, 12)
    ema26 = _ema(close, 26)
    macd = ema12 - ema26
    signal = _ema(macd, 9)
    hist = macd - signal
    return macd, signal, hist


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high = pd.to_numeric(df.get("High"), errors="coerce")
    low = pd.to_numeric(df.get("Low"), errors="coerce")
    close = pd.to_numeric(df.get("Close"), errors="coerce")
    prev_close = close.shift(1)

    tr = pd.concat(
        [
            (high - low).abs(),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)

    return tr.ewm(alpha=1 / period, adjust=False).mean().fillna(0)


def _trend_label(ma50: float, ma200: float, price: float) -> str:
    if price <= 0:
        return "غير متاح"
    if ma50 > ma200 and price > ma50:
        return "صاعد"
    if ma50 < ma200 and price < ma50:
        return "هابط"
    return "متذبذب"


def _support_resistance(df: pd.DataFrame, lookback: int = 60) -> Dict[str, float]:
    d = df.tail(max(lookback, 20)).copy()
    if d.empty:
        return {"support": 0.0, "resistance": 0.0}
    lo = pd.to_numeric(d["Low"], errors="coerce").dropna()
    hi = pd.to_numeric(d["High"], errors="coerce").dropna()
    if lo.empty or hi.empty:
        return {"support": 0.0, "resistance": 0.0}
    return {"support": float(lo.min()), "resistance": float(hi.max())}


# ============================================================
# ✅ Public API expected by Analysis page
# ============================================================

def self_test() -> Dict[str, Any]:
    """
    ✅ required by UI diagnostics
    لا نسوي اتصالات خارجية هنا حتى لا نفشل بسبب الشبكة.
    """
    return {
        "ok": True,
        "reason": "ok",
        "checks": {
            "generate_exists": callable(generate),
            "pandas_ok": True,
            "numpy_ok": True,
        },
    }


def diagnose() -> Dict[str, Any]:
    """
    Optional helper for UI
    """
    rep = self_test()
    if not rep.get("ok"):
        return rep
    rep["engine"] = "ai_engine.py"
    rep["note"] = "Engine is loaded and provides required functions."
    return rep


def generate(
    symbol: str,
    fin: Optional[Dict[str, Any]] = None,
    interval: str = "1d",
    period: Optional[str] = None,
    view_mode: str = "simple",
    user_rules: str = "",
    years: int = 5,
    **kwargs,
) -> Dict[str, Any]:
    """
    ✅ required by UI
    يرجع dict موحد لواجهة المستشار.
    - لا يرمي Exceptions للخارج (Fail-safe)
    """
    sym = get_ticker_symbol(symbol) if callable(get_ticker_symbol) else str(symbol or "").strip().upper()
    view_mode = str(view_mode or "simple").strip().lower()

    out: Dict[str, Any] = {
        "ok": False,
        "symbol": sym,
        "summary": "",
        "confidence": 0.35,
        "osoli_score": 0,
        "sections": {
            "financial": {},
            "technical": {},
            "classical": {},
            "thesis": {},
        },
        "scenarios": [],
        "warnings": [],
        "debug": {},
    }

    # ----------------------------
    # 1) Price history (Technical base)
    # ----------------------------
    df = pd.DataFrame()
    try:
        if callable(get_chart_history):
            df = get_chart_history(sym, period=period, interval=interval, years=years)  # type: ignore
    except Exception as e:
        out["warnings"].append(f"get_chart_history failed: {e}")

    if df is None or df.empty or "Close" not in df.columns:
        out["warnings"].append("لا توجد بيانات سعرية كافية (Close).")
        # still allow financial-only output
    else:
        close = pd.to_numeric(df["Close"], errors="coerce").dropna()
        if len(close) >= 30:
            ma50 = float(close.rolling(50).mean().iloc[-1]) if len(close) >= 50 else float(close.mean())
            ma200 = float(close.rolling(200).mean().iloc[-1]) if len(close) >= 200 else float(close.mean())
            last = float(close.iloc[-1])
            prev = float(close.iloc[-2]) if len(close) >= 2 else last
            chg = float(_pct(last, prev, 0.0) * 100)

            rsi14 = float(_rsi(close, 14).iloc[-1])
            macd, signal, hist = _macd(close)
            macd_v = float(macd.iloc[-1])
            sig_v = float(signal.iloc[-1])
            hist_v = float(hist.iloc[-1])

            atr14 = float(_atr(df, 14).iloc[-1]) if {"High", "Low", "Close"}.issubset(df.columns) else 0.0
            sr = _support_resistance(df, lookback=60)

            trend = _trend_label(ma50, ma200, last)

            out["sections"]["technical"] = {
                "price": last,
                "change_pct": chg,
                "ma50": ma50,
                "ma200": ma200,
                "trend": trend,
                "rsi14": rsi14,
                "macd": macd_v,
                "macd_signal": sig_v,
                "macd_hist": hist_v,
                "atr14": atr14,
            }

            out["sections"]["classical"] = {
                "support": sr.get("support", 0.0),
                "resistance": sr.get("resistance", 0.0),
            }

            # simple risk gates
            risk_flags: List[str] = []
            if rsi14 >= 75:
                risk_flags.append("RSI مرتفع (تشبع شراء)")
            if rsi14 <= 25 and rsi14 > 0:
                risk_flags.append("RSI منخفض (تشبع بيع)")
            if atr14 > 0 and last > 0 and (atr14 / last) > 0.06:
                risk_flags.append("تذبذب مرتفع (ATR%)")

            if risk_flags:
                out["warnings"] += risk_flags

    # ----------------------------
    # 2) Financials
    # ----------------------------
    fin_pack = {}
    try:
        if callable(get_fundamental_ratios):
            fin_pack = get_fundamental_ratios(sym)  # type: ignore
    except Exception as e:
        out["warnings"].append(f"fundamentals failed: {e}")

    if isinstance(fin_pack, dict) and fin_pack:
        out["sections"]["financial"] = fin_pack
    else:
        out["sections"]["financial"] = {"ok": False, "note": "لا توجد مؤشرات مالية متاحة."}

    # thesis
    try:
        if callable(get_thesis):
            th = get_thesis(sym)  # type: ignore
            if th is not None:
                out["sections"]["thesis"] = {
                    "thesis_text": str(getattr(th, "get", lambda k, d=None: d)("thesis_text", "") if isinstance(th, dict) else (th.get("thesis_text") if hasattr(th, "get") else "")),
                    "target_price": _safe_float(th.get("target_price")) if isinstance(th, dict) else 0.0,
                    "recommendation": str(th.get("recommendation")) if isinstance(th, dict) else "",
                    "last_updated": str(th.get("last_updated")) if isinstance(th, dict) else "",
                }
    except Exception:
        pass

    # Relative strength vs TASI (if available)
    try:
        if callable(get_relative_strength_vs_tasi):
            rs = get_relative_strength_vs_tasi(sym, period=None, interval="1d")  # type: ignore
            out["sections"]["technical"]["vs_tasi"] = rs
    except Exception:
        pass

    # ----------------------------
    # 3) User rules (optional)
    # ----------------------------
    rules_note = ""
    try:
        txt = str(user_rules or "").strip()
        if txt:
            # very lightweight "rule hints"
            hints = []
            tsec = out["sections"].get("technical", {}) or {}
            rsi_v = _safe_float(tsec.get("rsi14"))
            macd_h = _safe_float(tsec.get("macd_hist"))
            trend = str(tsec.get("trend") or "")

            if "RSI" in txt.upper():
                if "فوق" in txt and rsi_v >= 70:
                    hints.append("✅ شرط RSI فوق 70 متحقق")
                if "تحت" in txt and rsi_v <= 30:
                    hints.append("✅ شرط RSI تحت 30 متحقق")
            if "MACD" in txt.upper():
                if ("تقاطع" in txt or "cross" in txt.lower()) and macd_h > 0:
                    hints.append("✅ MACD إيجابي (هيستوجرام > 0)")
            if "ترند" in txt or "trend" in txt.lower():
                hints.append(f"ℹ️ الاتجاه الحالي: {trend}")

            rules_note = " | ".join(hints) if hints else "تم استلام القواعد (تقييم مبسط)."
    except Exception:
        pass

    # ----------------------------
    # 4) Osoli Score (simple composite, 0..10)
    # ----------------------------
    score = 0
    conf = 0.35

    try:
        # technical contribution
        tsec = out["sections"].get("technical", {}) or {}
        trend = str(tsec.get("trend") or "")
        rsi_v = _safe_float(tsec.get("rsi14"))
        if trend == "صاعد":
            score += 3
            conf += 0.15
        elif trend == "متذبذب":
            score += 1
            conf += 0.05

        if 45 <= rsi_v <= 65:
            score += 2
        elif rsi_v >= 70:
            score -= 1
        elif 0 < rsi_v <= 30:
            score += 1

        # financial contribution (if Piotroski exists)
        fsec = out["sections"].get("financial", {}) or {}
        piot = int(_safe_float(fsec.get("Piotroski_Score", 0)))
        if piot >= 7:
            score += 4
            conf += 0.20
        elif 4 <= piot <= 6:
            score += 2
            conf += 0.10
        elif piot > 0:
            score += 0
            conf += 0.05

        score = int(max(0, min(10, score)))
        conf = float(max(0.25, min(0.9, conf)))
    except Exception:
        score = int(max(0, min(10, score)))

    out["osoli_score"] = score
    out["confidence"] = conf

    # ----------------------------
    # 5) Scenarios (3)
    # ----------------------------
    scenarios: List[Dict[str, Any]] = []

    try:
        tsec = out["sections"].get("technical", {}) or {}
        csec = out["sections"].get("classical", {}) or {}
        price = _safe_float(tsec.get("price"))
        sup = _safe_float(csec.get("support"))
        res = _safe_float(csec.get("resistance"))
        atr14 = _safe_float(tsec.get("atr14"))

        # Conservative
        scenarios.append(
            {
                "name": "محافظ",
                "trigger": f"إغلاق فوق المتوسطات/تأكيد اتجاه",
                "entry": price,
                "stop": max(0.0, (sup - 0.5 * atr14) if sup > 0 else (price - 2 * atr14)),
                "tp": (res if res > 0 else (price + 3 * atr14)),
                "notes": "وقف قريب من الدعم مع هامش ATR.",
            }
        )

        # Balanced
        scenarios.append(
            {
                "name": "متوازن",
                "trigger": "اختراق مقاومة/استمرار زخم",
                "entry": price,
                "stop": max(0.0, (price - 2.5 * atr14) if atr14 > 0 else sup),
                "tp": (price + 4 * atr14) if atr14 > 0 else res,
                "notes": "يعتمد على استمرار الاتجاه وإدارة مخاطرة متوسطة.",
            }
        )

        # Aggressive
        scenarios.append(
            {
                "name": "هجومي",
                "trigger": "زخم عالي (MACD/RSI) + متابعة",
                "entry": price,
                "stop": max(0.0, (price - 3.5 * atr14) if atr14 > 0 else sup),
                "tp": (price + 6 * atr14) if atr14 > 0 else (res * 1.05 if res > 0 else price),
                "notes": "أعلى مخاطرة — مناسب للمضاربة فقط.",
            }
        )
    except Exception:
        # if no price data
        scenarios.append({"name": "متوازن", "trigger": "بيانات سعرية غير متاحة", "entry": 0, "stop": 0, "tp": 0})

    out["scenarios"] = scenarios

    # ----------------------------
    # 6) Summary text
    # ----------------------------
    try:
        tsec = out["sections"].get("technical", {}) or {}
        fsec = out["sections"].get("financial", {}) or {}
        trend = str(tsec.get("trend") or "غير متاح")
        rsi_v = _safe_float(tsec.get("rsi14"))
        piot = int(_safe_float(fsec.get("Piotroski_Score", 0)))

        summary_bits = [
            f"الاتجاه: {trend}",
        ]
        if rsi_v > 0:
            summary_bits.append(f"RSI: {rsi_v:.1f}")
        if piot > 0:
            summary_bits.append(f"F-Score: {piot}/9")
        summary_bits.append(f"Osoli Score: {score}/10")
        if rules_note:
            summary_bits.append(f"قواعدك: {rules_note}")

        out["summary"] = " | ".join(summary_bits)
        out["ok"] = True
    except Exception:
        out["summary"] = f"Osoli Score: {score}/10"
        out["ok"] = True

    # developer-friendly details
    if view_mode in ("dev", "developer", "json", "debug"):
        out["debug"] = {
            "interval": interval,
            "period": period,
            "view_mode": view_mode,
            "kwargs": {k: str(v)[:120] for k, v in (kwargs or {}).items()},
        }

    return out