# ai_engine/reporting.py
import traceback
import pandas as pd

from .config import AI_ENGINE_NAME, AI_ENGINE_VERSION
from .ohlcv import _ensure_ohlcv_columns
from .indicators import _compute_indicators
from .technicals import (
    _detect_advanced_patterns,
    _analyze_market_structure,
    _detect_liquidity_sweep,
    _detect_order_block,
    _analyze_ichimoku,
    _analyze_financial_golden_rules,
)
from .risk import (
    _analyze_sr,
    _risk_plan_from_atr_sr,
    _risk_gates,
    _build_scenarios,
    _calc_confidence,
    _build_explainability,
    _infer_strategy_hint,
)
from .user_rules import load_user_rules, _eval_user_rule
from .logging_learning import log_ai_signal, _get_weight

def _normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym

def _map_period_from_timeframe(timeframe: str):
    """
    ✅ إضافة: استخدام timeframe في اختيار فترة جلب البيانات (بدون كسر أي شيء)
    لأن get_chart_history عندك ممكن يدعم period فقط.
    """
    tf = (timeframe or "1D").upper().strip()
    if tf in ["1H", "60M", "H"]:
        return "60d"
    if tf in ["4H", "240M"]:
        return "180d"
    if tf in ["1W", "W"]:
        return "5y"
    if tf in ["1MO", "1M", "MO"]:
        return "10y"
    return "6mo"

def generate_ai_report(symbol, timeframe="1D"):
    symbol = _normalize_symbol(symbol)

    try:
        from market_data import get_chart_history

        # ✅ تطوير: timeframe يحدد فترة جلب البيانات
        period = _map_period_from_timeframe(timeframe)

        try:
            df = get_chart_history(symbol, period=period)
        except TypeError:
            df = get_chart_history(symbol, period)

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise ValueError("no data")

        df = _ensure_ohlcv_columns(df)
        if df is None or df.empty or len(df) < 60:
            raise ValueError("insufficient candles")

        ind = _compute_indicators(df)

        # المحركات الأساسية (كما عندك)
        s_candle, o_candle = _detect_advanced_patterns(df)
        s_struct, o_struct = _analyze_market_structure(df)
        s_sr, o_sr, f_sr = _analyze_sr(df)
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)

        # ✅ إضافة بدون حذف: تفعيل محركات موجودة عندك لكنها ما كانت داخلة في التقرير
        s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
        s_ob, o_ob, f_ob = _detect_order_block(df)
        s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)

        # تجميع التقني (إضافة محركات جديدة — بدون إزالة أي قديم)
        base_tech = (s_candle + s_struct + s_sr + s_liq + s_ob + s_ichi)

        tech_reasons = (o_struct or []) + (o_candle or []) + (o_sr or []) + (o_liq or []) + (o_ob or []) + (o_ichi or [])
        fund_reasons = o_fund or []

        # features
        features = {}
        fund_feats = (m_fund or {}).get("_fund_features", {}) if isinstance(m_fund, dict) else {}
        for d in [f_sr, fund_feats, f_liq, f_ob, f_ichi]:
            try:
                for k, v in (d or {}).items():
                    if isinstance(v, (bool, int)):
                        features[k] = int(v)
            except Exception:
                pass

        # أرقام مفيدة
        try:
            features["close"] = float(df["Close"].iloc[-1])
            if isinstance(ind.get("rsi14"), pd.Series):
                features["rsi14"] = float(ind["rsi14"].iloc[-1])
            if isinstance(ind.get("sma50"), pd.Series):
                features["sma50"] = float(ind["sma50"].iloc[-1])
            if isinstance(ind.get("sma200"), pd.Series) and not pd.isna(ind["sma200"].iloc[-1]):
                features["sma200"] = float(ind["sma200"].iloc[-1])
            if isinstance(ind.get("atr14"), pd.Series) and not pd.isna(ind["atr14"].iloc[-1]):
                features["atr14"] = float(ind["atr14"].iloc[-1])
            if ind.get("fib382") is not None:
                features["fib382"] = float(ind["fib382"])
        except Exception:
            pass

        # Weighted bonus للعوامل الثنائية
        weighted_bonus = 0.0
        for k, v in features.items():
            if isinstance(v, (bool, int)) and int(v) == 1:
                weighted_bonus += (0.2 * (_get_weight(k, 1.0) - 1.0))

        tech_score = float(base_tech + weighted_bonus)
        fund_score = float(s_fund)
        total_score = float(tech_score + fund_score)

        # قواعد المستخدم
        user_delta = 0.0
        try:
            rules = load_user_rules(enabled_only=True, max_rows=30)
        except Exception:
            rules = []

        if rules:
            for rr in rules:
                parsed = rr.get("parsed") or {}
                hit, delta, reason, f_user = _eval_user_rule(parsed, df, ind)
                if hit:
                    user_delta += float(delta)
                    if reason:
                        tech_reasons.append(reason)
                    for kk, vv in (f_user or {}).items():
                        features[kk] = int(vv)

        if abs(user_delta) > 0:
            tech_score = float(tech_score + user_delta)
            total_score = float(tech_score + fund_score)

        # Sector
        sector = None
        try:
            from market_data import get_static_info
            info = get_static_info(symbol) or {}
            if isinstance(info, dict):
                sector = info.get("sector") or info.get("Sector") or info.get("industry") or None
        except Exception:
            sector = None

        module_scores = {
            "MarketStructure": s_struct,
            "Candles": s_candle,
            "SupportResistance": s_sr,
            "LiquiditySweep": s_liq,
            "OrderBlock": s_ob,
            "Ichimoku": s_ichi,
            "Fundamental": s_fund,
            "UserRules": user_delta,
        }
        strategy_name = _infer_strategy_hint(module_scores)

        # Recommendation
        rec = "⚖️ محايد / مراقبة"
        clr = "#6c757d"
        strat = "السعر في منطقة حيرة. انتظر إشارة أوضح."

        if total_score >= 8:
            rec = "💎 فرصة ماسية (Strong Buy)"
            clr = "#198754"
            strat = "توافق قوي: هيكل + مناطق + إشارات قوة."
        elif total_score >= 4:
            rec = "✅ شراء / تجميع"
            clr = "#28a745"
            strat = "الإشارات الإيجابية تغلب."
        elif total_score <= -5:
            rec = "⛔ خروج / وقف خسارة"
            clr = "#dc3545"
            strat = "إشارات ضعف/كسر دعم/هيكل سلبي."
        elif tech_score > 4 and fund_score < 0:
            rec = "⚡ مضاربة بحذر"
            clr = "#ffc107"
            strat = "فني قوي لكن المالي ضعيف — تقليل مخاطرة."
        elif fund_score >= 4 and tech_score < 0:
            rec = "📉 استثمار قيمة"
            clr = "#0d6efd"
            strat = "مالي قوي والسعر ضعيف — مناسب للصبر."

        if not tech_reasons:
            tech_reasons = ["حركة السعر طبيعية"]
        if not fund_reasons:
            fund_reasons = ["المؤشرات المالية طبيعية"]

        confidence, confidence_label = _calc_confidence(tech_score, fund_score, df)
        explainability = _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score)
        explainability["confidence_note"] = f"Confidence={int(confidence)}% ({confidence_label})"

        # ✅ تطوير: الخطة حسب الاتجاه (لكن متوافق 100% لأن default buy)
        direction = "buy" if total_score >= 0 else "sell"
        risk_plan = _risk_plan_from_atr_sr(df, ind, direction=direction)

        # ✅ Engine meta for UI / debug (Base Interval الصحيح)
        try:
            last_idx = df.index[-1]
            last_bar = str(last_idx)
        except Exception:
            last_bar = None

        report = {
            "recommendation": rec,
            "color": clr,
            "strategy": strat,
            "tech_score": round(float(tech_score), 2),
            "fund_score": round(float(fund_score), 2),
            "tech_reasons": tech_reasons,
            "fund_reasons": fund_reasons,
            "trend": "صاعد" if float(tech_score) >= 0 else "هابط",
            "confidence": int(confidence),
            "confidence_label": confidence_label,
            "explainability": explainability,
            "features": features,
            "calibration": {},
            "strategy_name": strategy_name,
            "sector": sector,
            "risk_plan": risk_plan,

            # ✅ Added
            "engine_meta": {
                "engine": AI_ENGINE_NAME,
                "version": AI_ENGINE_VERSION,
                "timeframe": str(timeframe),
                "period_used": str(period),
                "rows": int(len(df)),
                "last_bar": last_bar,
            },
        }

        report["risk_gates"] = _risk_gates(report)
        report["scenarios"] = _build_scenarios(df, report)

        # تعديل التوصية إذا بوابات المخاطر رفضت
        try:
            if (not report["risk_gates"]["pass"]) and ("شراء" in str(report["recommendation"]) or "Buy" in str(report["recommendation"])):
                report["recommendation"] = "⚠️ إشارة موجودة لكن بوابات المخاطر رفضت"
                report["color"] = "#ffc107"
                report["strategy"] = "تم رفض التوصية بسبب: " + " | ".join(report["risk_gates"]["reasons"])
        except Exception:
            pass

        signal_id = log_ai_signal(symbol, timeframe, features, report, horizon_days=20, sector=sector, strategy_name=strategy_name)
        if signal_id:
            report["signal_id"] = signal_id

        return report

    except Exception as e:
        tr = traceback.format_exc()
        return {
            "__error__": str(e),
            "__trace__": tr,
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص بيانات أو خطأ داخلي",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "-",
            "confidence": 0,
            "confidence_label": "منخفضة",
            "explainability": {"positives": [], "negatives": [], "notes": ["AI Engine Error"]},
            "features": {},
            "calibration": {},
            "strategy_name": None,
            "sector": None,
            "risk_plan": {},
            "risk_gates": {"pass": False, "reasons": ["AI Engine Error"]},
            "scenarios": [],
            "engine_meta": {
                "engine": AI_ENGINE_NAME,
                "version": AI_ENGINE_VERSION,
                "timeframe": str(timeframe),
                "period_used": None,
                "rows": 0,
                "last_bar": None,
            },
        }
