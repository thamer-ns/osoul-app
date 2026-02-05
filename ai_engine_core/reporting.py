from osoli_logging import log_exception
# ai_engine_core/reporting.py

import traceback
import pandas as pd

from .config import AI_ENGINE_NAME, AI_ENGINE_VERSION
from .core import _normalize_symbol, _map_period_from_timeframe
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

# Optional technical modules (safe imports)
try:
    from .technicals import _detect_inside_bar
except Exception:
    _detect_inside_bar = None

try:
    from .technicals import _detect_gaps
except Exception:
    _detect_gaps = None

try:
    from .technicals import _detect_rsi_divergence
except Exception:
    _detect_rsi_divergence = None

try:
    from .technicals import _regime_hint_from_adx
except Exception:
    _regime_hint_from_adx = None

try:
    from .technicals import _vsa_lite
except Exception:
    _vsa_lite = None

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


def _timeframe_to_interval(timeframe: str) -> str:
    tf = str(timeframe or "").strip().upper()
    if tf in ("1H", "60M", "H"):
        return "60m"
    if tf in ("30M",):
        return "30m"
    if tf in ("15M",):
        return "15m"
    if tf in ("5M",):
        return "5m"
    if tf in ("1W", "W"):
        return "1wk"
    if tf in ("1M", "MO", "MONTH"):
        return "1mo"
    return "1d"


def _dedup_limit(items, limit=12):
    out, seen = [], set()
    for x in (items or []):
        s = str(x).strip()
        if not s:
            continue
        k = s.lower()
        if k in seen:
            continue
        out.append(s)
        seen.add(k)
        if len(out) >= limit:
            break
    return out


def _safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def generate_ai_report(symbol, timeframe="1D"):
    """Main public API used by views/shared.py

    Returns a dict with:
      recommendation/color/strategy
      tech_score/fund_score/total_score
      reasons, confidence, risk_gates, scenarios, risk_plan, engine_meta

    This file intentionally keeps backwards-compatible keys expected by the UI.
    """

    symbol = _normalize_symbol(symbol)

    try:
        from market_data import get_chart_history, get_static_info

        # Optional import (won't break if missing)
        try:
            from market_data import get_relative_strength_vs_tasi
        except Exception:
            get_relative_strength_vs_tasi = None

        period = _map_period_from_timeframe(timeframe)
        interval = _timeframe_to_interval(timeframe)

        # Fetch history with interval support (fallback for older signatures)
        try:
            df = get_chart_history(symbol, period=period, interval=interval)
        except TypeError:
            df = get_chart_history(symbol, period)

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            raise ValueError("no data")

        df = _ensure_ohlcv_columns(df)
        if df is None or df.empty:
            raise ValueError("no ohlcv")

        # Minimum candles based on interval
        min_rows = 60 if interval in ("1d", "1wk", "1mo") else 120
        if len(df) < min_rows:
            raise ValueError(f"insufficient candles ({len(df)}<{min_rows})")

        # Indicators pack
        ind = _compute_indicators(df)

        # =========================
        # Core tech modules
        # =========================
        s_candle, o_candle = _detect_advanced_patterns(df)
        s_struct, o_struct = _analyze_market_structure(df)
        s_sr, o_sr, f_sr = _analyze_sr(df)
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)

        s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
        s_ob, o_ob, f_ob = _detect_order_block(df)
        s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)

        # =========================
        # Optional tech add-ons
        # =========================
        s_inside, o_inside, f_inside = 0, [], {}
        if callable(_detect_inside_bar):
            try:
                s_inside, o_inside, f_inside = _detect_inside_bar(df)
            except Exception:
                s_inside, o_inside, f_inside = 0, [], {}

        s_gaps, o_gaps, f_gaps = 0, [], {}
        if callable(_detect_gaps):
            try:
                s_gaps, o_gaps, f_gaps = _detect_gaps(df)
            except Exception:
                s_gaps, o_gaps, f_gaps = 0, [], {}

        s_div, o_div, f_div = 0, [], {}
        if callable(_detect_rsi_divergence):
            try:
                s_div, o_div, f_div = _detect_rsi_divergence(df, ind)
            except Exception:
                s_div, o_div, f_div = 0, [], {}

        s_reg, o_reg, f_reg = 0, [], {}
        if callable(_regime_hint_from_adx):
            try:
                s_reg, o_reg, f_reg = _regime_hint_from_adx(ind)
            except Exception:
                s_reg, o_reg, f_reg = 0, [], {}

        s_vsa, o_vsa, f_vsa = 0, [], {}
        if callable(_vsa_lite):
            try:
                s_vsa, o_vsa, f_vsa = _vsa_lite(df)
            except Exception:
                s_vsa, o_vsa, f_vsa = 0, [], {}

        # =========================
        # Base score (tech)
        # =========================
        base_tech = (
            s_candle + s_struct + s_sr + s_liq + s_ob + s_ichi
            + s_inside + s_gaps + s_div + s_reg + s_vsa
        )

        tech_reasons = (
            (o_struct or []) + (o_candle or []) + (o_sr or [])
            + (o_liq or []) + (o_ob or []) + (o_ichi or [])
            + (o_inside or []) + (o_gaps or []) + (o_div or []) + (o_reg or []) + (o_vsa or [])
        )
        fund_reasons = o_fund or []

        # =========================
        # Features aggregation
        # =========================
        features = {}

        fund_feats = (m_fund or {}).get("_fund_features", {}) if isinstance(m_fund, dict) else {}
        for d in [f_sr, fund_feats, f_liq, f_ob, f_ichi, f_inside, f_gaps, f_div, f_reg, f_vsa]:
            try:
                for k, v in (d or {}).items():
                    if isinstance(v, (bool, int)):
                        features[str(k)] = int(v)
            except Exception as e:
                log_exception(e, "Ignored exception", level="DEBUG")
        # Numeric features (safe)
        try:
            features["close"] = float(df["Close"].iloc[-1])

            if isinstance(ind.get("rsi14"), pd.Series):
                features["rsi14"] = float(ind["rsi14"].iloc[-1])

            if isinstance(ind.get("macd"), pd.Series) and not pd.isna(ind["macd"].iloc[-1]):
                features["macd"] = float(ind["macd"].iloc[-1])

            if isinstance(ind.get("adx14"), pd.Series) and not pd.isna(ind["adx14"].iloc[-1]):
                features["adx14"] = float(ind["adx14"].iloc[-1])

            if isinstance(ind.get("sma50"), pd.Series) and not pd.isna(ind["sma50"].iloc[-1]):
                features["sma50"] = float(ind["sma50"].iloc[-1])

            if isinstance(ind.get("sma200"), pd.Series) and not pd.isna(ind["sma200"].iloc[-1]):
                features["sma200"] = float(ind["sma200"].iloc[-1])

            if isinstance(ind.get("atr14"), pd.Series) and not pd.isna(ind["atr14"].iloc[-1]):
                features["atr14"] = float(ind["atr14"].iloc[-1])

            if ind.get("fib382") is not None:
                features["fib382"] = float(ind["fib382"])
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
        # Relative strength vs TASI (optional)
        if get_relative_strength_vs_tasi is not None:
            try:
                rs = get_relative_strength_vs_tasi(symbol, period=None, interval="1d") or {}
                if rs.get("ok"):
                    features["rs_outperf_3m"] = _safe_float(rs.get("outperf_3m"), 0.0)
                    features["rs_outperf_1m"] = _safe_float(rs.get("outperf_1m"), 0.0)
                    features["rs_label"] = str(rs.get("label") or "")
                    if str(rs.get("label") or "").strip():
                        tech_reasons.append(f"📌 Relative Strength vs TASI: {rs.get('label')}")
            except Exception as e:
                log_exception(e, "Ignored exception", level="DEBUG")
        # Weighted bonus on boolean flags only
        weighted_bonus = 0.0
        for k, v in features.items():
            if isinstance(v, (bool, int)) and int(v) == 1:
                weighted_bonus += (0.2 * (_get_weight(k, 1.0) - 1.0))

        tech_score = float(base_tech + weighted_bonus)
        fund_score = float(s_fund)
        total_score = float(tech_score + fund_score)

        # =========================
        # User rules delta
        # =========================
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
                        try:
                            features[str(kk)] = int(vv)
                        except Exception as e:
                            log_exception(e, "Ignored exception", level="DEBUG")
        if abs(user_delta) > 0:
            tech_score = float(tech_score + user_delta)
            total_score = float(tech_score + fund_score)

        # Sector
        sector = None
        try:
            info = get_static_info(symbol) or {}
            if isinstance(info, dict):
                sector = info.get("sector") or info.get("Sector") or info.get("industry") or None
        except Exception:
            sector = None

        # module scores for strategy hint
        module_scores = {
            "MarketStructure": s_struct,
            "Candles": s_candle,
            "SupportResistance": s_sr,
            "LiquiditySweep": s_liq,
            "OrderBlock": s_ob,
            "Ichimoku": s_ichi,
            "InsideBar": s_inside,
            "Gaps": s_gaps,
            "Divergence": s_div,
            "Regime": s_reg,
            "VSA": s_vsa,
            "Fundamental": s_fund,
            "UserRules": user_delta,
        }
        strategy_name = _infer_strategy_hint(module_scores)

        # =========================
        # Recommendation mapping
        # =========================
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

        tech_reasons = _dedup_limit(tech_reasons, limit=12) or ["حركة السعر طبيعية"]
        fund_reasons = _dedup_limit(fund_reasons, limit=8) or ["المؤشرات المالية طبيعية"]

        confidence, confidence_label = _calc_confidence(tech_score, fund_score, df)
        try:
            confidence = float(confidence)
            if 0 <= confidence <= 1:
                confidence *= 100.0
        except Exception:
            confidence = 0.0

        explainability = _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score)
        explainability["confidence_note"] = f"Confidence={int(confidence)}% ({confidence_label})"

        # Better direction rule
        if total_score >= 2:
            direction = "buy"
        elif total_score <= -2:
            direction = "sell"
        else:
            direction = "neutral"

        risk_plan = _risk_plan_from_atr_sr(df, ind, direction=direction)

        try:
            last_bar = str(df.index[-1])
        except Exception:
            last_bar = None

        report = {
            "status": "ok",
            "recommendation": rec,
            "color": clr,
            "strategy": strat,
            "tech_score": round(float(tech_score), 2),
            "fund_score": round(float(fund_score), 2),
            "total_score": round(float(total_score), 2),
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
            "engine_meta": {
                "engine": AI_ENGINE_NAME,
                "version": AI_ENGINE_VERSION,
                "timeframe": str(timeframe),
                "period_used": str(period),
                "interval_used": str(interval),
                "rows": int(len(df)),
                "last_bar": last_bar,
            },
        }

        report["risk_gates"] = _risk_gates(report)
        report["scenarios"] = _build_scenarios(df, report)

        try:
            if (not report["risk_gates"]["pass"]) and ("شراء" in str(report["recommendation"]) or "Buy" in str(report["recommendation"])):
                report["recommendation"] = "⚠️ إشارة موجودة لكن بوابات المخاطر رفضت"
                report["color"] = "#ffc107"
                report["strategy"] = "تم رفض التوصية بسبب: " + " | ".join(report["risk_gates"]["reasons"])
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
        signal_id = log_ai_signal(
            symbol,
            timeframe,
            features,
            report,
            horizon_days=20,
            sector=sector,
            strategy_name=strategy_name,
        )
        if signal_id:
            report["signal_id"] = signal_id

        return report

    except Exception as e:
        tr = traceback.format_exc()
        base = {
            "status": "error",
            "__error__": str(e),
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
                "interval_used": None,
                "rows": 0,
                "last_bar": None,
            },
        }
        base["__trace__"] = tr
        return base
