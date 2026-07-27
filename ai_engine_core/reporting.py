from __future__ import annotations

# ai_engine_core/reporting.py

import traceback
from feature_flags import get_flag
import pandas as pd

from candle_confirmation import completed_candles
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
from .logging_learning import log_ai_signal, _get_weight, get_effective_weight

# Optional post-scoring gates/calibration (safe imports)
try:
    from .liquidity_gate import evaluate_liquidity_gate
except Exception:
    evaluate_liquidity_gate = None

try:
    from .multi_timeframe import evaluate_daily_weekly_alignment
except Exception:
    evaluate_daily_weekly_alignment = None

try:
    from .scoring_calibration import calibrate_score
except Exception:
    calibrate_score = None


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




def _build_signal_events(df: pd.DataFrame, ind: dict, limit: int = 12) -> list:
    """Create a compact list of recent technical 'events' for UI timeline."""
    events = []
    try:
        if df is None or df.empty:
            return events

        close = df["Close"]
        # SMA crosses
        sma50 = ind.get("sma50")
        sma200 = ind.get("sma200")
        if sma50 is not None and sma200 is not None and len(sma50) >= 3 and len(sma200) >= 3:
            prev = float(sma50.iloc[-2] - sma200.iloc[-2])
            curr = float(sma50.iloc[-1] - sma200.iloc[-1])
            if prev <= 0 and curr > 0:
                events.append({"type":"SMA Cross","event":"Golden Cross (50>200)","at": str(df.index[-1])})
            elif prev >= 0 and curr < 0:
                events.append({"type":"SMA Cross","event":"Death Cross (50<200)","at": str(df.index[-1])})

        # MACD cross
        macd = ind.get("macd")
        macd_sig = ind.get("macd_signal")
        if macd is not None and macd_sig is not None and len(macd) >= 3 and len(macd_sig) >= 3:
            prev = float(macd.iloc[-2] - macd_sig.iloc[-2])
            curr = float(macd.iloc[-1] - macd_sig.iloc[-1])
            if prev <= 0 and curr > 0:
                events.append({"type":"MACD","event":"MACD bullish cross","at": str(df.index[-1])})
            elif prev >= 0 and curr < 0:
                events.append({"type":"MACD","event":"MACD bearish cross","at": str(df.index[-1])})

        # RSI zones
        rsi = ind.get("rsi14")
        if rsi is not None and len(rsi) >= 2:
            r = float(rsi.iloc[-1])
            if r <= 30:
                events.append({"type":"RSI","event":f"Oversold (RSI {r:.1f})","at": str(df.index[-1])})
            elif r >= 70:
                events.append({"type":"RSI","event":f"Overbought (RSI {r:.1f})","at": str(df.index[-1])})

        # Close vs SMA20
        sma20 = ind.get("sma20")
        if sma20 is not None and len(sma20) >= 2 and len(close) >= 2:
            prev = float(close.iloc[-2] - sma20.iloc[-2])
            curr = float(close.iloc[-1] - sma20.iloc[-1])
            if prev <= 0 and curr > 0:
                events.append({"type":"Price","event":"Close crossed above SMA20","at": str(df.index[-1])})
            elif prev >= 0 and curr < 0:
                events.append({"type":"Price","event":"Close crossed below SMA20","at": str(df.index[-1])})
    except Exception:
        import logging
        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:130')

    return events[:limit]

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
            try:
                df = get_chart_history(symbol, period=period, interval=interval)
            except TypeError:
                df = get_chart_history(symbol, period)
        except Exception as e:
            return {
                "ok": False,
                "symbol": symbol,
                "timeframe": timeframe,
                "error": "history_error",
                "message": f"تعذر جلب البيانات السعرية: {type(e).__name__}. جرّب لاحقاً أو غيّر الفاصل.",
            }

        if df is None or (isinstance(df, pd.DataFrame) and df.empty):
            return {
                "ok": False,
                "symbol": symbol,
                "timeframe": timeframe,
                "error": "no_data",
                "message": "لا توجد بيانات سعرية كافية لهذا الرمز/الفاصل. تأكد من مفتاح Twelve Data أو جرّب فاصل زمني مختلف.",
            }

        df = _ensure_ohlcv_columns(df)
        if df is None or df.empty:
            return {
                "ok": False,
                "symbol": symbol,
                "timeframe": timeframe,
                "error": "no_ohlcv",
                "message": "لم نستطع بناء بيانات OHLCV (شموع) بشكل صحيح.",
            }

        raw_rows = int(len(df))
        df = completed_candles(df, interval=interval)
        confirmation_meta = dict(getattr(df, "attrs", {}).get("candle_confirmation") or {})
        if df.empty:
            return {
                "ok": False,
                "symbol": symbol,
                "timeframe": timeframe,
                "error": "no_closed_candles",
                "message": "لا توجد شمعة مكتملة بعد على هذا الفاصل. انتظر إغلاق الشمعة الحالية.",
            }

        # Minimum candles based on interval, after excluding the live candle.
        min_rows = 60 if interval in ("1d", "1wk", "1mo") else 120
        if len(df) < min_rows:
            return {
                "ok": False,
                "symbol": symbol,
                "timeframe": timeframe,
                "error": "insufficient_candles",
                "have": int(len(df)),
                "need": int(min_rows),
                "message": f"بيانات غير كافية لهذا الفاصل (تحتاج تقريباً {min_rows} شمعة أو أكثر).",
            }


        # Indicators pack
        ind = _compute_indicators(df)

        # Precompute UI helpers (safe) before report dict is constructed
        signal_events = []
        try:
            signal_events = _build_signal_events(df, ind, limit=12)
        except Exception:
            signal_events = []

        data_lineage = None
        try:
            data_lineage = getattr(df, "attrs", {}).get("data_lineage")
        except Exception:
            data_lineage = None

        why_wrong = []
        try:
            if df is None or df.empty or len(df) < 120:
                why_wrong.append("Coverage منخفض (بيانات قليلة)")
            if float(ind.get("atr_pct", 0) or 0) > 6:
                why_wrong.append("تذبذب مرتفع (ATR%)")
        except Exception:
            why_wrong = []

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
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:334')

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
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:361')

        # =========================
        # Advanced indicators (optional + cached)
        # =========================
        adv_pack = None
        try:
            from ai_engine_core.db import fetch_latest_advanced_indicators, save_advanced_indicators
            from technical_indicators import compute_advanced_technical_pack

            # Try cached result first
            cached = fetch_latest_advanced_indicators(symbol=symbol, interval=str(interval), max_age_minutes=180)
            if isinstance(cached, dict) and cached.get("payload"):
                adv_pack = cached.get("payload")

            if not isinstance(adv_pack, dict):
                adv_pack = compute_advanced_technical_pack(df, symbol=symbol, timeframe=str(interval))
                if isinstance(adv_pack, dict) and adv_pack.get("name"):
                    # store for reuse
                    try:
                        save_advanced_indicators(symbol=symbol, interval=str(interval), payload=adv_pack)
                    except Exception:
                        import logging
                        logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:383')

            # Merge numeric features
            if isinstance(adv_pack, dict):
                adv_feats = adv_pack.get("features") or {}
                for k, v in adv_feats.items():
                    if isinstance(v, (int, float)):
                        features[f"adv_{k}"] = float(v)

                # Evidence + signals
                for ev in (adv_pack.get("evidence") or []):
                    if isinstance(ev, str) and ev.strip():
                        tech_reasons.append(ev.strip())

                adv_conf = adv_pack.get("confidence")
                if isinstance(adv_conf, (int, float)):
                    features["adv_confidence"] = float(adv_conf)

                # If indicator returned errors, note them (but avoid spamming)
                errs = adv_pack.get("errors") or []
                if errs:
                    # show at most 2
                    for e in list(errs)[:2]:
                        if isinstance(e, str) and e.strip():
                            tech_reasons.append(f"⚠️ (مؤشرات متقدمة) {e.strip()}")
        except Exception:
            adv_pack = None

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
            except Exception:
                import logging
                logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:422')


        # =========================================================
        # 🧠 Learning context (Market trend + ADX regime + Sector)
        # =========================================================
        market_trend = None
        regime = None
        ctx_key = None
        horizons = None
        try:
            from market_data import get_tasi_history
            tasi = get_tasi_history(period=None, interval=str(interval))
            if tasi is not None and (not tasi.empty) and "Close" in tasi.columns and len(tasi) >= 80:
                c = pd.to_numeric(tasi["Close"], errors="coerce").dropna()
                ma50 = c.rolling(50).mean()
                # slope over last 20 bars
                slope20 = float((ma50.iloc[-1] - ma50.iloc[-21]) / ma50.iloc[-21]) if len(ma50.dropna()) > 21 and float(ma50.iloc[-21] or 0) != 0 else 0.0
                last = float(c.iloc[-1])
                last_ma = float(ma50.iloc[-1]) if pd.notna(ma50.iloc[-1]) else last
                if last > last_ma and slope20 > 0.01:
                    market_trend = "bull"
                elif last < last_ma and slope20 < -0.01:
                    market_trend = "bear"
                else:
                    market_trend = "sideways"
            else:
                market_trend = "UNK"
        except Exception:
            market_trend = "UNK"

        try:
            adxv = None
            if isinstance(ind, dict) and "adx14" in ind:
                adx = ind.get("adx14")
                if isinstance(adx, pd.Series) and len(adx) and pd.notna(adx.iloc[-1]):
                    adxv = float(adx.iloc[-1])
            if adxv is None:
                regime = "UNK"
            else:
                regime = "trend" if adxv >= 25 else "range"
        except Exception:
            regime = "UNK"

        # Sector (resolved before learning context)
        sector = None
        try:
            info = get_static_info(symbol) or {}
            if isinstance(info, dict):
                sector = info.get("sector") or info.get("Sector") or info.get("industry") or None
        except Exception:
            sector = None

        try:
            sec = str(sector) if sector else "UNK"
            ctx_key = f"mkt={market_trend}|reg={regime}|sec={sec}"
        except Exception:
            ctx_key = None

        # Multi-horizon evaluation defaults by timeframe
        try:
            tf = str(timeframe).lower().strip()
            if "wk" in tf or "week" in tf:
                horizons = [4, 8, 13, 26]
            else:
                horizons = [5, 10, 20, 60]
        except Exception:
            horizons = [5, 10, 20, 60]

        # Weighted bonus on boolean flags only
        weighted_bonus = 0.0
        for k, v in features.items():
            if isinstance(v, (bool, int)) and int(v) == 1:
                weighted_bonus += (0.2 * (get_effective_weight(k, ctx_key, 1.0) - 1.0))

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
                        except Exception:
                            import logging
                            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:513')

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

        # If advanced indicators are available, use their confidence as a small calibration factor
        # rather than overriding the main confidence.
        try:
            adv_c = features.get("adv_confidence")
            if isinstance(adv_c, (int, float)) and 0 <= float(adv_c) <= 100:
                # Map [0..100] around 50 -> [-7.5 .. +7.5]
                confidence = max(0.0, min(100.0, float(confidence) + (float(adv_c) - 50.0) * 0.15))
                confidence_label = f"{confidence_label} + مؤشرات متقدمة"
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:594')

        # =========================
        # ✅ Liquidity Gate + MTF Alignment + Score Normalization
        # =========================
        calibration_payload = {}
        liquidity_gate_res = None
        mtf_alignment_res = None
        score_calibration_res = None

        # 1) score normalization by timeframe/sector (confidence tuning + strong-call guard)
        try:
            if callable(calibrate_score):
                score_calibration_res = calibrate_score(float(total_score), timeframe=str(timeframe), sector=sector)
                if isinstance(score_calibration_res, dict):
                    calibration_payload["score_normalization"] = score_calibration_res
                    if score_calibration_res.get("available"):
                        try:
                            confidence = max(0.0, min(100.0, float(confidence) + float(score_calibration_res.get("confidence_delta") or 0.0)))
                        except Exception:
                            import logging
                            logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
                        if score_calibration_res.get("percentile") is not None:
                            try:
                                features["score_percentile"] = float(score_calibration_res.get("percentile"))
                            except Exception:
                                import logging
                                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
                        if score_calibration_res.get("zscore") is not None:
                            try:
                                features["score_z"] = float(score_calibration_res.get("zscore"))
                            except Exception:
                                import logging
                                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
                        if (not bool(score_calibration_res.get("strong_ok", True))) and (("Strong" in str(rec)) or ("💎" in str(rec))):
                            rec = "⚠️ شراء بحذر / مراقبة"
                            clr = "#ffc107"
                            strat = "تم تخفيف التوصية: السكور الحالي أقل من المعتاد مقارنة بتاريخ نفس الفاصل/القطاع."
                            tech_reasons.append("📊 تطبيع السكور: القوة الحالية ليست عالية بما يكفي تاريخيًا لإشارة قوية.")
        except Exception:
            try:
                import logging
                logging.getLogger(__name__).exception("score normalization gate failed")
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)

        # 2) liquidity gate (execution realism)
        try:
            if callable(evaluate_liquidity_gate):
                liquidity_gate_res = evaluate_liquidity_gate(df)
                if isinstance(liquidity_gate_res, dict):
                    calibration_payload["liquidity_gate"] = liquidity_gate_res
                    for k, v in (liquidity_gate_res.get("features") or {}).items():
                        features[str(k)] = v
                    cap = liquidity_gate_res.get("confidence_cap")
                    if isinstance(cap, (int, float)):
                        confidence = min(float(confidence), float(cap))
                    for rr in (liquidity_gate_res.get("reasons") or []):
                        tech_reasons.append(str(rr))
                    liq_pass = bool(liquidity_gate_res.get("pass", True))
                    if (not liq_pass) and (("Strong" in str(rec)) or ("💎" in str(rec)) or ("شراء" in str(rec)) or ("مضاربة" in str(rec))):
                        rec = "⚠️ إشارة موجودة لكن السيولة ضعيفة"
                        clr = "#ffc107"
                        strat = "تم تخفيف التوصية لأن سيولة السهم منخفضة وقد تجعل التنفيذ أصعب وأكثر خطورة."
        except Exception:
            try:
                import logging
                logging.getLogger(__name__).exception("liquidity gate failed")
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)

        # 3) daily/weekly alignment gate (top-down confirmation)
        try:
            _interval_l = str(interval or "").lower().strip()
            if callable(evaluate_daily_weekly_alignment) and _interval_l in {"1d", "d", "day", "daily"}:
                _bias = "buy" if float(total_score) >= 2 else ("sell" if float(total_score) <= -2 else "neutral")
                mtf_alignment_res = evaluate_daily_weekly_alignment(df, daily_bias=_bias)
                if isinstance(mtf_alignment_res, dict):
                    calibration_payload["multi_timeframe"] = mtf_alignment_res
                    try:
                        confidence = max(0.0, min(100.0, float(confidence) + float(mtf_alignment_res.get("confidence_delta") or 0.0)))
                    except Exception:
                        import logging
                        logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
                    features["mtf_applied"] = 1 if bool(mtf_alignment_res.get("applied")) else 0
                    features["mtf_aligned"] = 1 if bool(mtf_alignment_res.get("aligned")) else 0
                    if str(mtf_alignment_res.get("reason") or "").strip():
                        tech_reasons.append(str(mtf_alignment_res.get("reason")))
                    if (not bool(mtf_alignment_res.get("aligned", True))) and (_bias == "buy") and (("Strong" in str(rec)) or ("💎" in str(rec)) or ("شراء" in str(rec)) or ("مضاربة" in str(rec))):
                        rec = "⚠️ شراء بحذر / مراقبة"
                        clr = "#ffc107"
                        strat = "تم تخفيف التوصية بسبب تعارض الاتجاه اليومي مع الاتجاه الأسبوعي."
        except Exception:
            try:
                import logging
                logging.getLogger(__name__).exception("multi-timeframe gate failed")
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)

        # =========================
        # ✅ Data Quality Gate -> calibrate confidence + refuse strong recommendations
        # =========================
        dq = None
        try:
            from financial_analysis.data_quality import assess_fundamental_quality

            dq = assess_fundamental_quality(symbol, period_type="Annual")
        except Exception:
            dq = None

        if isinstance(dq, dict):
            try:
                dq_score = int(dq.get("score") or 0)
                dq_pass = bool(dq.get("pass"))
            except Exception:
                dq_score, dq_pass = 0, False

            # expose to UI/engine
            features["dq_score"] = dq_score
            features["dq_pass"] = 1 if dq_pass else 0

            # confidence cap + label
            if not dq_pass:
                confidence = min(55.0, float(confidence))
                confidence_label = f"{confidence_label} + جودة بيانات ضعيفة"

        # Low confidence should prevent "strong" calls
        try:
            is_strong_like = ("Strong" in str(rec)) or ("💎" in str(rec)) or ("شراء" in str(rec))
            if is_strong_like and float(confidence) < 55:
                rec = "⚠️ إشارة ضعيفة — مراقبة"
                clr = "#ffc107"
                strat = "الثقة منخفضة أو البيانات ناقصة — لا نعطي توصية قوية حتى تتحسن الجودة/الاكتمال."
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:631')

        # If data quality FAIL, force downgrade for buy/value calls
        try:
            if isinstance(dq, dict) and (not bool(dq.get("pass"))):
                if ("Strong" in str(rec)) or ("شراء" in str(rec)) or ("استثمار" in str(rec)):
                    rec = "⚠️ مراقبة — البيانات المالية غير كافية"
                    clr = "#ffc107"
                    strat = "تم تخفيض قوة التوصية بسبب فشل بوابة جودة البيانات (نقص/عدم اتساق)."
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:641')

        tech_reasons = _dedup_limit(tech_reasons, limit=12) or ["حركة السعر طبيعية"]
        fund_reasons = _dedup_limit(fund_reasons, limit=8) or ["المؤشرات المالية طبيعية"]

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
            "calibration": calibration_payload if isinstance(calibration_payload, dict) else {},
            "strategy_name": strategy_name,
            "sector": sector,
            "risk_plan": risk_plan,
            "learning_context": {"market_trend": market_trend, "regime": regime, "ctx_key": ctx_key},
            "engine_meta": {
                "engine": AI_ENGINE_NAME,
                "version": AI_ENGINE_VERSION,
                "timeframe": str(timeframe),
                "period_used": str(period),
                "interval_used": str(interval),
                "rows": int(len(df)),
                "raw_rows": raw_rows,
                "last_bar": last_bar,
                "confirmation_mode": "closed_only",
                "excluded_incomplete_bars": int(
                    confirmation_meta.get("excluded_incomplete_bars", 0) or 0
                ),
            },
        }

        # Attach multi-timeframe helpers
        report["signal_events"] = signal_events or []
        report["engine_meta"]["why_wrong"] = (why_wrong or [])[:5]
        if isinstance(calibration_payload, dict) and calibration_payload:
            report["engine_meta"]["calibration_applied"] = list(calibration_payload.keys())
        if data_lineage:
            report["engine_meta"]["data_lineage"] = data_lineage

        report["risk_gates"] = _risk_gates(report)
        report["scenarios"] = _build_scenarios(df, report)

        try:
            if (not report["risk_gates"]["pass"]) and ("شراء" in str(report["recommendation"]) or "Buy" in str(report["recommendation"])):
                report["recommendation"] = "⚠️ إشارة موجودة لكن بوابات المخاطر رفضت"
                report["color"] = "#ffc107"
                report["strategy"] = "تم رفض التوصية بسبب: " + " | ".join(report["risk_gates"]["reasons"])
        except Exception:
            import logging
            logging.getLogger(__name__).exception('Suppressed Exception exception replaced with logging at ai_engine_core/reporting.py:707')

        signal_id = None
        try:
            if get_flag("enable_self_learning", True):
                signal_id = log_ai_signal(
                    symbol=symbol,
                    timeframe=timeframe,
                    features=dict(features or {}),
                    report=dict(report or {}),
                    sector=sector,
                    strategy_name=strategy_name,
                    market_trend=market_trend,
                    regime=regime,
                    ctx_key=ctx_key,
                    horizons=horizons,
                )
        except Exception as e:
            try:
                import logging
                logging.getLogger(__name__).warning("log_ai_signal failed: %s", e)
            except Exception:
                import logging
                logging.getLogger(__name__).debug("Best-effort operation failed", exc_info=True)
            signal_id = None

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
