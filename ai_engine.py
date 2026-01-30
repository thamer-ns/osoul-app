# ai_engine.py
import json
import pandas as pd
import numpy as np

from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🧠 AI Memory (DB Logging + Simple Online Learning)
# ============================================================

def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None

def _ensure_ai_tables():
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    try:
        execute_query("""
        CREATE TABLE IF NOT EXISTS ai_signals (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMP DEFAULT NOW(),
            symbol TEXT,
            timeframe TEXT,
            horizon_days INT DEFAULT 20,
            features_json TEXT,
            report_json TEXT,
            outcome_return_pct DOUBLE PRECISION,
            outcome_win INT
        )
        """, ())
        execute_query("""
        CREATE TABLE IF NOT EXISTS ai_weights (
            id SERIAL PRIMARY KEY,
            key TEXT UNIQUE,
            weight DOUBLE PRECISION DEFAULT 1.0,
            updated_at TIMESTAMP DEFAULT NOW()
        )
        """, ())
        return True
    except Exception:
        return False

def log_ai_signal(symbol, timeframe, features: dict, report: dict, horizon_days=20):
    """يسجل كل تقرير (features + report) للرجوع له لاحقاً وتطوير الذكاء."""
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()
    try:
        execute_query(
            "INSERT INTO ai_signals (symbol, timeframe, horizon_days, features_json, report_json) VALUES (%s,%s,%s,%s,%s)",
            (str(symbol), str(timeframe), int(horizon_days), json.dumps(features, ensure_ascii=False), json.dumps(report, ensure_ascii=False)),
        )
        return True
    except Exception:
        return False

def update_ai_outcome(signal_id: int, outcome_return_pct: float):
    """تحديث نتيجة إشارة قديمة (تستخدم لاحقاً للتعلّم)."""
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    try:
        win = 1 if float(outcome_return_pct) > 0 else 0
        execute_query(
            "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s WHERE id=%s",
            (float(outcome_return_pct), int(win), int(signal_id)),
        )
        return True
    except Exception:
        return False

def _get_weight(key: str, default=1.0):
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return float(default)
    _ensure_ai_tables()
    try:
        df = fetch_table("ai_weights")
        if df is None or df.empty or "key" not in df.columns:
            return float(default)
        row = df[df["key"] == key]
        if row.empty:
            return float(default)
        return float(row.iloc[0].get("weight", default))
    except Exception:
        return float(default)

def _set_weight(key: str, weight: float):
    execute_query, fetch_table = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()
    try:
        # upsert
        execute_query(
            """
            INSERT INTO ai_weights (key, weight) VALUES (%s,%s)
            ON CONFLICT (key) DO UPDATE SET weight=EXCLUDED.weight, updated_at=NOW()
            """,
            (str(key), float(weight)),
        )
        return True
    except Exception:
        return False

def learn_from_history(max_rows=400):
    """
    تعلّم بسيط: إذا الإشارات التي تحتوي feature_key كانت رابحة غالباً => زِد وزنها قليلاً،
    وإذا كانت خاسرة غالباً => قلّل وزنها.
    هذا ليس ML ثقيل، لكنه Online-Tuning مفيد جداً ومستقر.
    """
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()
    try:
        df = fetch_table("ai_signals")
        if df is None or df.empty:
            return {"ok": True, "updated": 0}

        df = df.dropna(subset=["outcome_win"])
        if df.empty:
            return {"ok": True, "updated": 0}

        df = df.sort_values("created_at", ascending=False).head(int(max_rows))

        # اجمع معدلات الفوز لكل feature_key موجودة
        stats = {}
        for _, r in df.iterrows():
            try:
                feats = json.loads(r.get("features_json") or "{}")
                win = int(r.get("outcome_win") or 0)
                for k, v in feats.items():
                    # نهتم فقط بالFeatures البوليانية/الإشارات
                    if isinstance(v, (bool, int)) and int(v) in (0, 1):
                        stats.setdefault(k, {"wins": 0, "n": 0})
                        stats[k]["wins"] += win
                        stats[k]["n"] += 1
            except Exception:
                pass

        updated = 0
        for k, s in stats.items():
            if s["n"] < 20:
                continue
            win_rate = s["wins"] / s["n"]
            w = _get_weight(k, 1.0)

            # تعديل لطيف جداً حتى لا يسبب تقلبات
            if win_rate >= 0.58:
                w = min(w + 0.05, 2.0)
            elif win_rate <= 0.42:
                w = max(w - 0.05, 0.3)

            if _set_weight(k, w):
                updated += 1

        return {"ok": True, "updated": updated, "features": len(stats)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ============================================================
# 🕯️ 1) Advanced Candlestick Patterns (موجود + ثابت)
# ============================================================

def _detect_advanced_patterns(df):
    if df is None or len(df) < 5:
        return 0, []

    score = 0
    patterns = []

    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    body1 = abs(c1["Close"] - c1["Open"])
    body2 = abs(c2["Close"] - c2["Open"])

    is_c1_red = c1["Close"] < c1["Open"]
    is_c1_green = c1["Close"] > c1["Open"]
    is_c2_red = c2["Close"] < c2["Open"]
    is_c3_green = c3["Close"] > c3["Open"]
    is_c3_red = c3["Close"] < c3["Open"]

    # Morning Star
    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = c1["Open"] - (body1 / 2)
        if c3["Close"] > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح - انعكاس إيجابي قوي")

    # Evening Star
    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = c1["Open"] + (body1 / 2)
        if c3["Close"] < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء - خروج/انعكاس سلبي")

    # Bullish Harami
    if is_c2_red and is_c3_green and c3["Open"] > c2["Close"] and c3["Close"] < c2["Open"]:
        score += 2
        patterns.append("🤰 الحرامي الشرائي - ضعف الزخم الهابط")

    # Bullish Engulfing
    if is_c2_red and is_c3_green and c3["Open"] < c2["Close"] and c3["Close"] > c2["Open"]:
        score += 2
        patterns.append("🔥 ابتلاع شرائي - سيطرة مشترين")

    return score, patterns


# ============================================================
# 📈 2) Market Structure + BMS/Retest/OTE (مطوّر)
# ============================================================

def _pivot_points(series, left=3, right=3, mode="high"):
    """
    استخراج قمم/قيعان سوينغ بسيطة.
    mode: 'high' => pivot highs, 'low' => pivot lows
    """
    if series is None or len(series) < left + right + 3:
        return []
    pivots = []
    arr = series.values
    for i in range(left, len(arr) - right):
        window = arr[i - left : i + right + 1]
        if mode == "high":
            if arr[i] == np.max(window):
                pivots.append((i, float(arr[i])))
        else:
            if arr[i] == np.min(window):
                pivots.append((i, float(arr[i])))
    return pivots

def _analyze_market_structure(df):
    if df is None or len(df) < 60:
        return 0, []

    score = 0
    obs = []

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    curr = float(close.iloc[-1])

    # آخر قمة/قاع سوينغ
    ph = _pivot_points(high, 3, 3, "high")
    pl = _pivot_points(low, 3, 3, "low")

    last_swing_high = ph[-1][1] if ph else float(high.iloc[-25:-2].max())
    last_swing_low = pl[-1][1] if pl else float(low.iloc[-25:-2].min())

    # BMS (Break Market Structure)
    if curr > last_swing_high:
        score += 3
        obs.append(f"🚀 BMS: كسر قمة سوينغ ({last_swing_high:.2f})")
    elif curr < last_swing_low:
        score -= 3
        obs.append(f"⚠️ BMS: كسر قاع سوينغ ({last_swing_low:.2f})")
    else:
        # داخل نطاق
        rng = last_swing_high - last_swing_low
        if rng > 0:
            pos = (curr - last_swing_low) / rng
            if pos > 0.8:
                score += 1
                obs.append("السعر قرب سقف النطاق (مراقبة اختراق)")
            elif pos < 0.2:
                score -= 1
                obs.append("السعر قرب قاع النطاق (حذر)")
            else:
                score -= 1
                obs.append("مسار عرضي (تذبذب)")

    # Retest + OTE(تقريبياً قرب 50% من موجة الكسر)
    # نلتقط آخر موجة واضحة من سوينغ لو لِسوينغ هاي أو العكس
    try:
        # آخر سوينغين
        if len(ph) >= 1 and len(pl) >= 1:
            last_high_i, last_high = ph[-1]
            last_low_i, last_low = pl[-1]
            if last_low_i < last_high_i:
                # موجة صاعدة: low -> high
                impulse_low = last_low
                impulse_high = last_high
                fib50 = impulse_low + 0.5 * (impulse_high - impulse_low)
                if abs(curr - fib50) / max(curr, 1e-9) < 0.01:
                    score += 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة دخول أفضل)")
            else:
                # موجة هابطة
                impulse_high = last_high
                impulse_low = last_low
                fib50 = impulse_high - 0.5 * (impulse_high - impulse_low)
                if abs(curr - fib50) / max(curr, 1e-9) < 0.01:
                    score -= 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة بيع أفضل)")
    except Exception:
        pass

    return score, obs


# ============================================================
# 🧩 3) Smart Money: Liquidity Sweep + Order Block + AMD (مطوّر)
# ============================================================

def _detect_liquidity_sweep(df, lookback=30):
    """
    صيد السيولة = اختراق زائف (wick sweep):
    - Sweep High: high يكسر أعلى قمة، لكن الإغلاق يرجع تحت القمة
    - Sweep Low: low يكسر أدنى قاع، لكن الإغلاق يرجع فوق القاع
    """
    if df is None or len(df) < lookback + 5:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"liq_sweep_high": 0, "liq_sweep_low": 0}

    recent = df.iloc[-(lookback + 1):-1]
    prev_high = float(recent["High"].max())
    prev_low = float(recent["Low"].min())

    last = df.iloc[-1]
    h = float(last["High"])
    l = float(last["Low"])
    c = float(last["Close"])

    # Sweep highs -> غالباً يسبق هبوط (Sniper Sell)
    if h > prev_high and c < prev_high:
        score -= 2
        feats["liq_sweep_high"] = 1
        obs.append("🧲 صيد سيولة شرائية (اختراق زائف للأعلى)")

    # Sweep lows -> غالباً يسبق صعود (Sniper Buy)
    if l < prev_low and c > prev_low:
        score += 2
        feats["liq_sweep_low"] = 1
        obs.append("🧲 صيد سيولة بيعية (اختراق زائف للأسفل)")

    return score, obs, feats

def _detect_order_block(df):
    """
    أوردر بلوك مبسط:
    - Bullish OB: آخر شمعة هابطة قبل اندفاع صاعد قوي
    - Bearish OB: آخر شمعة صاعدة قبل اندفاع هابط قوي
    ثم نبحث هل السعر رجع داخل منطقة الشمعة (retest)
    """
    if df is None or len(df) < 80:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"bull_ob_retest": 0, "bear_ob_retest": 0}

    close = df["Close"].astype(float)
    open_ = df["Open"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    # نحدد "اندفاع" عبر شمعة كبيرة مقارنة بمتوسط المدى
    rng = (high - low)
    avg_rng = float(rng.iloc[-40:].mean()) if len(rng) >= 40 else float(rng.mean())

    # ابحث عن اندفاع صاعد قوي في آخر 25 شمعة
    window = df.iloc[-25:]
    idx_impulse_up = None
    for i in range(len(window) - 1, 1, -1):
        r = float(window["High"].iloc[i] - window["Low"].iloc[i])
        if r > avg_rng * 1.4 and float(window["Close"].iloc[i]) > float(window["Open"].iloc[i]):
            idx_impulse_up = window.index[i]
            break

    if idx_impulse_up is not None:
        # آخر شمعة هابطة قبلها = OB
        sub = df.loc[:idx_impulse_up].tail(15)
        bears = sub[sub["Close"] < sub["Open"]]
        if not bears.empty:
            ob_idx = bears.index[-1]
            ob_low = float(low.loc[ob_idx])
            ob_high = float(high.loc[ob_idx])
            last_c = float(close.iloc[-1])
            last_l = float(low.iloc[-1])
            # retest = لمس المنطقة
            if (last_l <= ob_high) and (last_c >= ob_low):
                score += 2
                feats["bull_ob_retest"] = 1
                obs.append("🧱 Bullish Order Block retest (منطقة شراء محتملة)")

    # اندفاع هابط
    idx_impulse_dn = None
    for i in range(len(window) - 1, 1, -1):
        r = float(window["High"].iloc[i] - window["Low"].iloc[i])
        if r > avg_rng * 1.4 and float(window["Close"].iloc[i]) < float(window["Open"].iloc[i]):
            idx_impulse_dn = window.index[i]
            break

    if idx_impulse_dn is not None:
        sub = df.loc[:idx_impulse_dn].tail(15)
        bulls = sub[sub["Close"] > sub["Open"]]
        if not bulls.empty:
            ob_idx = bulls.index[-1]
            ob_low = float(low.loc[ob_idx])
            ob_high = float(high.loc[ob_idx])
            last_c = float(close.iloc[-1])
            last_h = float(high.iloc[-1])
            if (last_h >= ob_low) and (last_c <= ob_high):
                score -= 2
                feats["bear_ob_retest"] = 1
                obs.append("🧱 Bearish Order Block retest (منطقة بيع محتملة)")

    return score, obs, feats


# ============================================================
# ☁️ 4) Ichimoku Trend Filter (مطوّر)
# ============================================================

def _ichimoku(df):
    """
    Ichimoku standard:
    Tenkan(9), Kijun(26), SpanB(52), SpanA shift 26, SpanB shift 26, Chikou = close shift -26
    """
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)

    return tenkan, kijun, span_a, span_b, chikou

def _analyze_ichimoku(df):
    if df is None or len(df) < 120:
        return 0, [], {}

    score = 0
    obs = []
    feats = {
        "ichi_bull": 0,
        "ichi_bear": 0,
        "ichi_tk_cross_up": 0,
        "ichi_tk_cross_dn": 0,
    }

    tenkan, kijun, span_a, span_b, chikou = _ichimoku(df)
    close = df["Close"].astype(float)

    c = float(close.iloc[-1])
    sa = float(span_a.iloc[-1]) if not pd.isna(span_a.iloc[-1]) else np.nan
    sb = float(span_b.iloc[-1]) if not pd.isna(span_b.iloc[-1]) else np.nan

    # cloud top/bottom
    if np.isnan(sa) or np.isnan(sb):
        return 0, [], feats

    cloud_top = max(sa, sb)
    cloud_bot = min(sa, sb)

    # Chikou مقارنة بالسعر (تقريبياً)
    try:
        chik = float(chikou.iloc[-27])  # لأن shift(-26)
        price_26 = float(close.iloc[-27])
    except Exception:
        chik = None
        price_26 = None

    # اتجاه صاعد: السعر فوق السحابة + سحابة صعودية + الشينكو فوق السعر
    if c > cloud_top:
        score += 1
        obs.append("☁️ السعر فوق سحابة الكومو (Bias شرائي)")
    elif c < cloud_bot:
        score -= 1
        obs.append("☁️ السعر تحت سحابة الكومو (Bias بيعي)")
    else:
        obs.append("☁️ السعر داخل السحابة (تذبذب/ضعف ترند)")

    # TK Cross
    if float(tenkan.iloc[-1]) > float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) <= float(kijun.iloc[-2]):
        score += 1
        feats["ichi_tk_cross_up"] = 1
        obs.append("🔀 تقاطع تنكن فوق كيجن (إشارة دعم للشراء)")
    if float(tenkan.iloc[-1]) < float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) >= float(kijun.iloc[-2]):
        score -= 1
        feats["ichi_tk_cross_dn"] = 1
        obs.append("🔀 تقاطع تنكن تحت كيجن (إشارة دعم للبيع)")

    # Bull/Bear full (شروط أقوى)
    if (c > cloud_top) and (float(span_a.iloc[-1]) > float(span_b.iloc[-1])) and (chik is not None) and (price_26 is not None) and (chik > price_26):
        score += 2
        feats["ichi_bull"] = 1
        obs.append("✅ Ichimoku صاعد قوي (شينكو+سحابة+سعر)")
    if (c < cloud_bot) and (float(span_a.iloc[-1]) < float(span_b.iloc[-1])) and (chik is not None) and (price_26 is not None) and (chik < price_26):
        score -= 2
        feats["ichi_bear"] = 1
        obs.append("⛔ Ichimoku هابط قوي (شينكو+سحابة+سعر)")

    return score, obs, feats


# ============================================================
# 💰 5) Fundamental Golden Rules (موجود + ثابت)
# ============================================================

def _analyze_financial_golden_rules(symbol):
    try:
        metrics = get_advanced_fundamental_ratios(symbol)
    except Exception:
        return 0, [], {}

    score = 0
    obs = []
    feats = {
        "fund_strong_piotroski": 0,
        "fund_weak_piotroski": 0,
        "fund_graham_fair": 0,
        "fund_neg_ocf": 0,
    }

    try:
        piotroski = metrics.get("Piotroski_Score", 0)
        if piotroski >= 7:
            score += 3
            feats["fund_strong_piotroski"] = 1
            obs.append("💎 Piotroski مرتفع (ملاءة/جودة أرباح قوية)")
        elif piotroski <= 3:
            score -= 3
            feats["fund_weak_piotroski"] = 1
            obs.append("❌ Piotroski منخفض (هشاشة مالية)")

        fv = metrics.get("Fair_Value_Graham", 0)
        rating = metrics.get("Rating", "")
        if fv and fv > 0 and ("قوي" in str(rating) or "جيد" in str(rating)):
            score += 2
            feats["fund_graham_fair"] = 1
            obs.append("✅ تقييم جراهام جيد/عادل")

        ops_str = str(metrics.get("Opinions", ""))
        if ("سالب" in ops_str) and (("تشغيلي" in ops_str) or ("نقد" in ops_str)):
            score -= 4
            feats["fund_neg_ocf"] = 1
            obs.append("⚠️ التدفق النقدي التشغيلي سالب")
    except Exception:
        pass

    return score, obs, {**metrics, "_fund_features": feats}


# ============================================================
# 📊 6) VSA (مطوّر أكثر)
# ============================================================

def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 50:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"vsa_upthrust": 0, "vsa_stopping_volume": 0, "vsa_distribution": 0}

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)
    open_ = df["Open"].astype(float)
    vol = df["Volume"].astype(float)

    curr = df.iloc[-1]
    avg_vol = float(vol.iloc[-20:].mean())
    rng = (high - low)
    avg_rng = float(rng.iloc[-20:].mean())

    # Upthrust (ضعف): شمعة صاعدة كبيرة + حجم عالي + إغلاق قريب من القاع
    r = float(curr["High"] - curr["Low"])
    if (float(curr["Close"]) > float(curr["Open"])) and (float(curr["Volume"]) > avg_vol * 1.5) and (r > avg_rng * 1.2):
        if float(curr["Close"]) <= float(curr["Low"]) + 0.25 * r:
            score -= 2
            feats["vsa_upthrust"] = 1
            obs.append("VSA: Upthrust (ضعف/تصريف محتمل)")

    # Stopping Volume (قوة): شمعة هابطة + حجم عالي + إغلاق في المنتصف/أعلى
    if (float(curr["Close"]) < float(curr["Open"])) and (float(curr["Volume"]) > avg_vol * 1.5) and (r > avg_rng * 1.1):
        if float(curr["Close"]) >= float(curr["Low"]) + 0.5 * r:
            score += 2
            feats["vsa_stopping_volume"] = 1
            obs.append("VSA: Stopping Volume (امتصاص بيع/قوة)")

    # Distribution قرب نهاية حركة صاعدة: حجم عالي + إغلاق بعيد عن القمة
    # (مبسطة وفق وصف “تفريغ على نشاط”)
    if float(curr["Volume"]) > avg_vol * 1.7:
        if float(curr["Close"]) < float(curr["Low"]) + 0.55 * r and float(curr["Close"]) > float(curr["Open"]):
            score -= 1
            feats["vsa_distribution"] = 1
            obs.append("VSA: تفريغ محتمل (حجم عالي وإغلاق ليس على القمة)")

    return score, obs, feats


# ============================================================
# 🧱 7) Support/Resistance Zones (مبسطة)
# ============================================================

def _support_resistance_zones(df, lookback=120, max_levels=6):
    """
    استخراج مستويات مناطق الدعم/المقاومة عبر pivots ثم دمجها لمناطق.
    """
    if df is None or len(df) < lookback:
        return [], []

    h = df["High"].astype(float)
    l = df["Low"].astype(float)

    ph = _pivot_points(h.tail(lookback), 3, 3, "high")
    pl = _pivot_points(l.tail(lookback), 3, 3, "low")

    highs = [p[1] for p in ph][-max_levels:]
    lows = [p[1] for p in pl][-max_levels:]

    return lows, highs

def _analyze_sr(df):
    if df is None or len(df) < 120:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"near_support": 0, "near_resistance": 0, "broke_support_confirm": 0}

    close = float(df["Close"].astype(float).iloc[-1])
    lows, highs = _support_resistance_zones(df)

    if lows:
        sup = min(lows, key=lambda x: abs(close - x))
        if abs(close - sup) / max(close, 1e-9) < 0.01:
            score += 1
            feats["near_support"] = 1
            obs.append("🧩 قرب منطقة دعم (Zone)")

        # تأكيد كسر الدعم: إغلاق يومين تحت الدعم (قاعدة عملية)
        try:
            c1 = float(df["Close"].iloc[-1])
            c2 = float(df["Close"].iloc[-2])
            if (c1 < sup) and (c2 < sup):
                score -= 2
                feats["broke_support_confirm"] = 1
                obs.append("🧨 كسر دعم مؤكد (إغلاق يومين تحت المنطقة)")
        except Exception:
            pass

    if highs:
        res = min(highs, key=lambda x: abs(close - x))
        if abs(close - res) / max(close, 1e-9) < 0.01:
            score -= 1
            feats["near_resistance"] = 1
            obs.append("🧩 قرب منطقة مقاومة (Zone)")

    return score, obs, feats


# ============================================================
# ✅ Confidence + Explainability (كما عندك + يدعم Features)
# ============================================================

def _calc_confidence(tech_score, fund_score, df):
    quality = 5
    if df is not None and len(df) >= 220:
        quality = 30
    elif df is not None and len(df) >= 120:
        quality = 25
    elif df is not None and len(df) >= 60:
        quality = 15

    strength = min(abs(tech_score + fund_score) * 8, 45)
    alignment = 25 if ((tech_score >= 0 and fund_score >= 0) or (tech_score <= 0 and fund_score <= 0)) else 10

    conf = int(min(quality + strength + alignment, 100))
    if conf >= 75:
        label = "عالية"
    elif conf >= 50:
        label = "متوسطة"
    else:
        label = "منخفضة"
    return conf, label

def _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score):
    positives, negatives, notes = [], [], []
    pos_keys = ["اختراق", "BMS", "OTE", "نجمة", "ابتلاع", "قوة", "Order Block", "Ichimoku صاعد", "Bias شرائي", "Stopping", "دعم", "✅", "💎", "🔀 تقاطع"]

    for x in (tech_reasons or []):
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    for x in (fund_reasons or []):
        (positives if any(k in x for k in pos_keys) else negatives).append(x)

    notes.append(f"Tech={tech_score} | Fund={fund_score} | Total={total_score}")
    if tech_score > 3 and fund_score < 0:
        notes.append("تعارض: الفني قوي لكن المالي ضعيف — الأفضل مضاربة بإدارة مخاطر.")
    if fund_score > 3 and tech_score < 0:
        notes.append("تعارض: المالي قوي لكن السعر ضعيف — مناسب لاستثمار قيمة بصبر.")

    return {"positives": positives[:10], "negatives": negatives[:10], "notes": notes[:10]}


# ============================================================
# 🧠 Master Brain (مطوّر: يضيف Ichimoku + SMC + SR + Weights)
# ============================================================

def generate_ai_report(symbol, timeframe="1D"):
    """
    يرجع نفس مفاتيحك الأساسية + إضافات:
    - signals/features قابلة للتسجيل
    """
    try:
        df = get_chart_history(symbol, period="6mo")
        if df is None or df.empty:
            raise ValueError("no data")

        # نظافة الأعمدة
        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                raise ValueError(f"missing {col}")

        # 1) Candles
        s_candle, o_candle = _detect_advanced_patterns(df)

        # 2) Market Structure
        s_struct, o_struct = _analyze_market_structure(df)

        # 3) SMC
        s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
        s_ob, o_ob, f_ob = _detect_order_block(df)

        # 4) Ichimoku
        s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)

        # 5) VSA
        s_vsa, o_vsa, f_vsa = _analyze_vsa_art_of_trading(df)

        # 6) SR Zones
        s_sr, o_sr, f_sr = _analyze_sr(df)

        # 7) Fundamentals
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)

        # ------------------------------------------
        # 🔧 Weighted Tech Score (قابل للتعلّم)
        # كل feature_key نضربه في وزن قابل للتعديل من التاريخ
        # ------------------------------------------
        base_tech = s_candle + s_struct + s_vsa + s_ichi + s_ob + s_liq + s_sr
        tech_reasons = (o_struct or []) + (o_candle or []) + (o_vsa or []) + (o_ichi or []) + (o_ob or []) + (o_liq or []) + (o_sr or [])

        # اجمع Features بولاين/0-1
        features = {}
        # fund features داخل metrics
        fund_feats = (m_fund or {}).get("_fund_features", {})
        for d in [f_liq, f_ob, f_ichi, f_vsa, f_sr, fund_feats]:
            try:
                for k, v in (d or {}).items():
                    if isinstance(v, (bool, int)):
                        features[k] = int(v)
            except Exception:
                pass

        # وزن features (تعلّم لاحقاً)
        weighted_bonus = 0.0
        for k, v in features.items():
            if int(v) == 1:
                weighted_bonus += (0.2 * (_get_weight(k, 1.0) - 1.0))

        tech_score = float(base_tech + weighted_bonus)
        fund_score = float(s_fund)
        total_score = float(tech_score + fund_score)

        # ------------------------------------------
        # القرار (يحافظ على منطقك مع حساسية أعلى)
        # ------------------------------------------
        rec = "⚖️ محايد / مراقبة"
        clr = "#6c757d"
        strat = "السعر في منطقة حيرة. انتظر إشارة أوضح."

        if total_score >= 8:
            rec = "💎 فرصة ماسية (Strong Buy)"
            clr = "#198754"
            strat = "توافق قوي: هيكل + فلتر ترند + إشارات قوة."
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

        fund_reasons = o_fund or []
        if not tech_reasons:
            tech_reasons = ["حركة السعر طبيعية"]
        if not fund_reasons:
            fund_reasons = ["المؤشرات المالية طبيعية"]

        confidence, confidence_label = _calc_confidence(tech_score, fund_score, df)
        explainability = _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score)

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
            "features": features,  # مفيد للعرض/التعلّم
        }

        # ✅ يسجّل ذاكرة بشكل آمن (إذا DB متوفر)
        log_ai_signal(symbol, timeframe, features, report, horizon_days=20)

        return report

    except Exception:
        return {
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص بيانات",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "-",
            "confidence": 0,
            "confidence_label": "منخفضة",
            "explainability": {"positives": [], "negatives": [], "notes": ["AI Engine Error"]},
            "features": {},
        }


# ============================================================
# 🛡️ Portfolio Intelligence (كما عندك)
# ============================================================

def calculate_portfolio_risk_score(trades_df, cash_percent):
    try:
        if trades_df is None or trades_df.empty:
            return 0

        open_trades = trades_df[trades_df["status"] == "Open"]
        if open_trades.empty:
            return 0

        total_market_val = float(open_trades["market_value"].sum())
        if total_market_val == 0:
            return 0

        max_asset_weight = (float(open_trades["market_value"].max()) / total_market_val) * 100
        concentration_score = 30 if max_asset_weight > 50 else (15 if max_asset_weight > 25 else 0)

        liquidity_score = 25 if cash_percent < 5 else (10 if cash_percent < 15 else 0)

        strategy_score = 0
        try:
            spec_ratio = len(open_trades[open_trades["strategy"].astype(str).str.contains("مضاربة", na=False)]) / len(open_trades)
            strategy_score = spec_ratio * 30
        except Exception:
            pass

        return min(round(concentration_score + liquidity_score + strategy_score, 1), 100)
    except Exception:
        return 50


def run_stress_test(portfolio_value, open_positions_df):
    try:
        if open_positions_df is None or open_positions_df.empty:
            return {"scenarios": [], "insight": "المحفظة كاش."}

        weighted_beta = 0
        total_val = float(open_positions_df["market_value"].sum())
        if total_val == 0:
            return {"scenarios": [], "insight": "غير متاح"}

        for _, row in open_positions_df.iterrows():
            w = float(row["market_value"]) / total_val
            if row.get("asset_type") == "Sukuk":
                b = 0.1
            elif "مضاربة" in str(row.get("strategy", "")):
                b = 1.2
            else:
                b = 0.9
            weighted_beta += (w * b)

        scenarios = [
            {"name": "انهيار (-20%)", "market_chg": -0.20, "color": "#8B0000"},
            {"name": "تصحـيح (-10%)", "market_chg": -0.10, "color": "#DC2626"},
            {"name": "انتعـاش (+10%)", "market_chg": 0.10, "color": "#059669"},
            {"name": "طفرة (+20%)", "market_chg": 0.20, "color": "#047857"},
        ]

        results = []
        for s in scenarios:
            impact_pct = s["market_chg"] * weighted_beta
            results.append({"scenario": s["name"], "impact_pct": impact_pct * 100, "color": s["color"]})

        insight = "المحفظة عالية التذبذب" if weighted_beta > 1.1 else "المحفظة متوازنة"
        return {"scenarios": results, "insight": insight}
    except Exception:
        return {"scenarios": [], "insight": "غير متاح"}


def generate_rebalancing_suggestions(trades_df, cash_pct):
    suggestions = []
    try:
        if cash_pct < 5:
            suggestions.append(("priority", "🚨 السيولة منخفضة جداً (< 5%)"))

        if trades_df is not None and not trades_df.empty:
            open_trades = trades_df[trades_df["status"] == "Open"]
            for _, row in open_trades.iterrows():
                if float(row.get("gain_pct", 0) or 0) < -10:
                    suggestions.append(("danger", f"🛑 خسارة تجاوزت -10% في {row.get('symbol','-')}"))
    except Exception:
        pass

    return suggestions
