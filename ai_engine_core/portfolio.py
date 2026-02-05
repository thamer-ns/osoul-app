from osoli_logging import log_exception
# ai_engine_core/portfolio.py

import math
import logging
log = logging.getLogger("osooli")
from typing import Dict, Any, List, Tuple, Optional

import pandas as pd


# =========================================================
# 🧩 Helpers (Safe)
# =========================================================
def _sf(x, default=0.0) -> float:
    try:
        if x is None:
            return float(default)
        if isinstance(x, str):
            s = x.replace("%", "").replace(",", "").strip()
            if s.lower() in ("nan", "none", ""):
                return float(default)
            return float(s)
        return float(x)
    except Exception:
        return float(default)


def _clamp(x, lo=0.0, hi=100.0):
    try:
        return max(lo, min(hi, float(x)))
    except Exception:
        return lo


def _safe_div(a, b, default=0.0):
    try:
        a = float(a)
        b = float(b)
        if b == 0:
            return default
        return a / b
    except Exception:
        return default


def _get_open_trades(trades_df: pd.DataFrame) -> pd.DataFrame:
    if trades_df is None or trades_df.empty:
        return pd.DataFrame()
    if "status" not in trades_df.columns:
        return pd.DataFrame()
    return trades_df[trades_df["status"].astype(str).str.lower().eq("open")].copy()


def _infer_sector(row: pd.Series) -> str:
    for k in ["sector", "Sector", "industry", "Industry"]:
        if k in row.index and str(row.get(k) or "").strip():
            return str(row.get(k)).strip()
    return "Unknown"


def _infer_strategy(row: pd.Series) -> str:
    s = str(row.get("strategy", "") or "").strip()
    return s if s else "Unknown"


def _infer_asset_type(row: pd.Series) -> str:
    s = str(row.get("asset_type", "") or "").strip()
    return s if s else "Equity"


# =========================================================
# ✅ 1) Portfolio Risk Score (upgraded, but same signature)
# =========================================================
def calculate_portfolio_risk_score(trades_df, cash_percent):
    """
    ترجع رقم 0..100
    0 = محفظة منخفضة المخاطر/كاش
    100 = محفظة عالية المخاطر

    ✅ تطوير بدون كسر:
    - نفس الدالة ونفس المدخلات/المخرجات
    - منطق أقوى: تركيز + سيولة + مضاربة + عدد المراكز + خسائر كبيرة
    """
    try:
        # Defensive
        cash_pct = _sf(cash_percent, 0.0)
        open_trades = _get_open_trades(trades_df)

        if open_trades.empty:
            return 0

        if "market_value" not in open_trades.columns:
            # حاول احتسابها من الكمية والسعر (بدون نتائج وهمية)
            qty_col = "quantity" if "quantity" in open_trades.columns else ("qty" if "qty" in open_trades.columns else None)
            price_col = "current_price" if "current_price" in open_trades.columns else ("market_price" if "market_price" in open_trades.columns else ("price" if "price" in open_trades.columns else ("entry_price" if "entry_price" in open_trades.columns else None)))
            if qty_col and price_col:
                q = pd.to_numeric(open_trades[qty_col], errors="coerce").fillna(0)
                p = pd.to_numeric(open_trades[price_col], errors="coerce").fillna(0)
                open_trades["market_value"] = q * p
            else:
                return None
        mv = pd.to_numeric(open_trades["market_value"], errors="coerce").fillna(0.0).astype(float)
        total_mv = float(mv.sum())
        if total_mv <= 0:
            return 0

        # Weights
        w = mv / total_mv
        max_w = float(w.max()) if len(w) else 0.0
        top3 = float(w.sort_values(ascending=False).head(3).sum()) if len(w) >= 3 else float(w.sum())

        # 1) Concentration risk
        # max position weight + top-3 concentration
        concentration_score = 0.0
        if max_w >= 0.50:
            concentration_score += 35
        elif max_w >= 0.30:
            concentration_score += 22
        elif max_w >= 0.20:
            concentration_score += 12

        if top3 >= 0.75:
            concentration_score += 18
        elif top3 >= 0.60:
            concentration_score += 10

        # 2) Liquidity risk (cash)
        liquidity_score = 0.0
        if cash_pct < 5:
            liquidity_score = 22
        elif cash_pct < 10:
            liquidity_score = 14
        elif cash_pct < 15:
            liquidity_score = 8

        # 3) Strategy risk (speculation ratio)
        strategy_score = 0.0
        try:
            if "strategy" in open_trades.columns:
                strat = open_trades["strategy"].astype(str)
                spec_ratio = float((strat.str.contains("مضاربة", na=False)).sum()) / max(len(open_trades), 1)
                # 0..30
                strategy_score = _clamp(spec_ratio * 30, 0, 30)
        except Exception:
            strategy_score = 0.0

        # 4) Positions count (too many micro-positions can be chaotic)
        n = int(len(open_trades))
        positions_score = 0.0
        if n >= 18:
            positions_score = 8
        elif n >= 12:
            positions_score = 5
        elif n <= 3:
            # very concentrated portfolio (already partly captured), add tiny penalty
            positions_score = 3

        # 5) Deep drawdowns in open positions (if gain_pct exists)
        dd_score = 0.0
        if "gain_pct" in open_trades.columns:
            gp = pd.to_numeric(open_trades["gain_pct"], errors="coerce").fillna(0.0).astype(float)
            # count large losers
            losers_10 = int((gp <= -10).sum())
            losers_20 = int((gp <= -20).sum())
            dd_score += min(12, losers_10 * 3)
            dd_score += min(10, losers_20 * 2)

        total = concentration_score + liquidity_score + strategy_score + positions_score + dd_score
        return float(_clamp(round(total, 1), 0, 100))

    except Exception as e:
        try:
            log.exception("calculate_portfolio_risk_score failed")
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
        return None


# =========================================================
# ✅ 2) Stress Test (upgraded, same signature)
# =========================================================
def run_stress_test(portfolio_value, open_positions_df):
    """
    Stress test بسيط لكن أذكى:
    - Weighted beta proxy من strategy + asset_type
    - يضيف سيناريوهات إضافية (gap, slow bleed) بشكل آمن
    - يرجع نفس البنية: {scenarios:[], insight:""}
    """
    try:
        if open_positions_df is None or open_positions_df.empty:
            return {"scenarios": [], "insight": "المحفظة كاش."}

        if "market_value" not in open_positions_df.columns:
            return {"scenarios": [], "insight": "غير متاح"}

        mv = pd.to_numeric(open_positions_df["market_value"], errors="coerce").fillna(0.0).astype(float)
        total_val = float(mv.sum())
        if total_val <= 0:
            return {"scenarios": [], "insight": "غير متاح"}

        # Beta proxy rules:
        # - Sukuk ~ 0.1
        # - Speculation "مضاربة" ~ 1.25
        # - Normal equity ~ 0.95
        # - Unknown / high-risk ~ 1.05
        weighted_beta = 0.0
        for _, row in open_positions_df.iterrows():
            w = _safe_div(_sf(row.get("market_value", 0.0), 0.0), total_val, 0.0)
            asset_type = _infer_asset_type(row)
            strat = _infer_strategy(row)

            if str(asset_type).lower() == "sukuk":
                b = 0.10
            elif "مضاربة" in str(strat):
                b = 1.25
            else:
                b = 0.95

            # Optional extra: if position is already losing big -> behaves worse in stress
            gp = _sf(row.get("gain_pct", 0.0), 0.0)
            if gp <= -15:
                b *= 1.08

            weighted_beta += (w * b)

        scenarios = [
            {"name": "انهيار (-20%)", "market_chg": -0.20, "color": "#8B0000"},
            {"name": "تصحـيح (-10%)", "market_chg": -0.10, "color": "#DC2626"},
            {"name": "نزيف بطيء (-6%)", "market_chg": -0.06, "color": "#EF4444"},
            {"name": "انتعـاش (+10%)", "market_chg": 0.10, "color": "#059669"},
            {"name": "طفرة (+20%)", "market_chg": 0.20, "color": "#047857"},
        ]

        results = []
        for s in scenarios:
            impact_pct = float(s["market_chg"]) * float(weighted_beta)
            results.append(
                {
                    "scenario": s["name"],
                    "impact_pct": impact_pct * 100.0,
                    "color": s["color"],
                }
            )

        if weighted_beta >= 1.20:
            insight = "المحفظة عالية التذبذب (ميول مضاربية/حساسية للسوق)"
        elif weighted_beta <= 0.60:
            insight = "المحفظة دفاعية (حساسية منخفضة للسوق)"
        else:
            insight = "المحفظة متوازنة"

        return {"scenarios": results, "insight": insight}

    except Exception:
        return {"scenarios": [], "insight": "غير متاح"}


# =========================================================
# ✅ 3) Rebalancing Suggestions (upgraded, same signature)
# =========================================================
def generate_rebalancing_suggestions(trades_df, cash_pct):
    """
    يرجع list of tuples: (level, text)
    level in: priority / danger / warn / info
    """
    suggestions: List[Tuple[str, str]] = []
    try:
        cash_pct = _sf(cash_pct, 0.0)
        open_trades = _get_open_trades(trades_df)

        # Cash gates
        if cash_pct < 5:
            suggestions.append(("priority", "🚨 السيولة منخفضة جداً (< 5%) — ارفع الكاش أو خفف مراكز"))
        elif cash_pct < 10:
            suggestions.append(("warn", "⚠️ السيولة منخفضة (< 10%) — احتفظ بهامش فرص/مخاطر"))

        if open_trades.empty:
            suggestions.append(("info", "💤 لا توجد مراكز مفتوحة حالياً"))
            return suggestions

        if "market_value" not in open_trades.columns:
            suggestions.append(("warn", "⚠️ لا يوجد market_value لحساب التركيز/إعادة التوازن"))
            return suggestions

        mv = pd.to_numeric(open_trades["market_value"], errors="coerce").fillna(0.0).astype(float)
        total_mv = float(mv.sum())
        if total_mv <= 0:
            return suggestions

        w = mv / total_mv
        max_w = float(w.max()) if len(w) else 0.0

        # Concentration suggestions
        if max_w >= 0.45:
            sym = "-"
            try:
                idx = int(w.idxmax())
                sym = str(open_trades.loc[idx].get("symbol", "-"))
            except Exception as e:
                log_exception(e, "Ignored exception", level="DEBUG")
            suggestions.append(("danger", f"🎯 تركّز عالي: أكبر مركز ≈ {max_w*100:.1f}% ({sym}) — خفف/وزّع"))

        # Loss control suggestions
        if "gain_pct" in open_trades.columns:
            gp = pd.to_numeric(open_trades["gain_pct"], errors="coerce").fillna(0.0).astype(float)
            big_losers = open_trades[gp <= -10]
            for _, row in big_losers.iterrows():
                suggestions.append(("danger", f"🛑 خسارة تجاوزت -10% في {row.get('symbol','-')} — راجع وقف الخسارة/الحجم"))

            mid_losers = open_trades[(gp < -5) & (gp > -10)]
            for _, row in mid_losers.iterrows():
                suggestions.append(("warn", f"⚠️ خسارة بين -5% و-10% في {row.get('symbol','-')} — مراقبة"))

        # Strategy balance suggestions
        try:
            if "strategy" in open_trades.columns:
                strat = open_trades["strategy"].astype(str)
                spec_cnt = int(strat.str.contains("مضاربة", na=False).sum())
                n = int(len(open_trades))
                if n > 0:
                    spec_ratio = spec_cnt / n
                    if spec_ratio >= 0.60:
                        suggestions.append(("warn", "⚡ نسبة المضاربة مرتفعة (>60%) — خفف تذبذب المحفظة أو ارفع كاش"))
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
        # Sector balance (if sector exists)
        if any(c in open_trades.columns for c in ["sector", "Sector", "industry", "Industry"]):
            try:
                sectors = open_trades.apply(_infer_sector, axis=1)
                open_trades["_sector_norm"] = sectors
                sector_mv = open_trades.groupby("_sector_norm")["market_value"].sum().sort_values(ascending=False)
                if not sector_mv.empty:
                    top_sector = str(sector_mv.index[0])
                    top_share = float(sector_mv.iloc[0]) / total_mv
                    if top_share >= 0.55 and top_sector != "Unknown":
                        suggestions.append(("warn", f"🏷️ تركّز قطاعي: {top_sector} ≈ {top_share*100:.1f}% — فكر بالتنويع"))
            except Exception as e:
                log_exception(e, "Ignored exception", level="DEBUG")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return suggestions


# =========================================================
# ⭐ إضافات اختيارية (لا تكسر أي شيء)
# =========================================================
def suggest_position_size(
    account_value: float,
    entry: float,
    stop: float,
    risk_pct: float = 1.0,
    lot_size: float = 1.0,
) -> Dict[str, Any]:
    """
    Position Sizing بسيط:
    - risk_pct من قيمة المحفظة (مثلاً 1%)
    - qty = (account_value * risk_pct) / (entry - stop)
    """
    out = {"ok": False, "qty": 0.0, "risk_amount": 0.0, "risk_per_share": 0.0, "note": ""}

    try:
        acc = _sf(account_value, 0.0)
        e = _sf(entry, 0.0)
        s = _sf(stop, 0.0)
        rp = _sf(risk_pct, 1.0)

        if acc <= 0 or e <= 0 or s <= 0:
            out["note"] = "قيم غير صالحة"
            return out

        rps = abs(e - s)
        if rps <= 0:
            out["note"] = "الوقف مساوي للدخول"
            return out

        risk_amount = acc * (rp / 100.0)
        qty = risk_amount / rps

        if lot_size and lot_size > 0:
            qty = math.floor(qty / lot_size) * lot_size

        out.update(
            {
                "ok": True,
                "qty": float(max(0.0, qty)),
                "risk_amount": float(risk_amount),
                "risk_per_share": float(rps),
                "note": "حجم مركز وفق نسبة مخاطرة",
            }
        )
        return out
    except Exception:
        return out


def portfolio_risk_gates(trades_df, cash_percent) -> Dict[str, Any]:
    """
    بوابات مخاطرة للمحفظة:
    - تركّز شديد
    - كاش منخفض جدًا
    - خسائر كبيرة متراكمة
    """
    gates = {"pass": True, "reasons": [], "risk_score": 0.0}

    try:
        score = calculate_portfolio_risk_score(trades_df, cash_percent)
        gates["risk_score"] = float(score)

        open_trades = _get_open_trades(trades_df)
        cash_pct = _sf(cash_percent, 0.0)

        if cash_pct < 3:
            gates["pass"] = False
            gates["reasons"].append("السيولة أقل من 3% — خطر تسييل عالي")

        if open_trades is not None and not open_trades.empty and "market_value" in open_trades.columns:
            mv = pd.to_numeric(open_trades["market_value"], errors="coerce").fillna(0.0).astype(float)
            total = float(mv.sum())
            if total > 0:
                max_w = float((mv.max() / total))
                if max_w > 0.55:
                    gates["pass"] = False
                    gates["reasons"].append("تركيز أعلى من 55% في مركز واحد — خطر كبير")

        if open_trades is not None and not open_trades.empty and "gain_pct" in open_trades.columns:
            gp = pd.to_numeric(open_trades["gain_pct"], errors="coerce").fillna(0.0).astype(float)
            if int((gp <= -20).sum()) >= 2:
                gates["pass"] = False
                gates["reasons"].append("مركزين أو أكثر بخسارة أكبر من -20% — راجع إدارة المخاطر")

        # score-based soft gate
        if float(score) >= 75 and gates["pass"]:
            gates["reasons"].append("مستوى المخاطر مرتفع (>=75) — يفضّل تخفيف/رفع كاش")

    except Exception:
        gates["pass"] = False
        gates["reasons"].append("تعذر تقييم بوابات المخاطر")

    return gates
