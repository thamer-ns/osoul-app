# ai_engine_core/technicals.py

import numpy as np
import pandas as pd


# =========================================================
# 🧩 Utilities
# =========================================================
def _sf(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _col(df, name):
    if df is None or df.empty or name not in df.columns:
        return None
    return pd.to_numeric(df[name], errors="coerce").astype(float)


def _has_ohlcv(df):
    if df is None or df.empty:
        return False
    need = {"Open", "High", "Low", "Close"}
    return all(c in df.columns for c in need)


# =========================================================
# ✨ Candlestick patterns (existing) — with safety
# =========================================================
def _detect_advanced_patterns(df):
    if df is None or len(df) < 5 or not _has_ohlcv(df):
        return 0, []

    score = 0
    patterns = []

    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    o1, h1, l1, cl1 = map(_sf, [c1["Open"], c1["High"], c1["Low"], c1["Close"]])
    o2, h2, l2, cl2 = map(_sf, [c2["Open"], c2["High"], c2["Low"], c2["Close"]])
    o3, h3, l3, cl3 = map(_sf, [c3["Open"], c3["High"], c3["Low"], c3["Close"]])

    body1 = abs(cl1 - o1)
    body2 = abs(cl2 - o2)

    is_c1_red = cl1 < o1
    is_c1_green = cl1 > o1
    is_c2_red = cl2 < o2
    is_c3_green = cl3 > o3
    is_c3_red = cl3 < o3

    # Morning star
    if is_c1_red and (body2 < body1 * 0.4) and is_c3_green:
        midpoint = o1 - (body1 / 2.0)
        if cl3 > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح - انعكاس إيجابي قوي")

    # Evening star
    if is_c1_green and (body2 < body1 * 0.4) and is_c3_red:
        midpoint = o1 + (body1 / 2.0)
        if cl3 < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء - خروج/انعكاس سلبي")

    # Harami / weakness downtrend
    if is_c2_red and is_c3_green and (o3 > cl2) and (cl3 < o2):
        score += 2
        patterns.append("🤰 الحرامي الشرائي - ضعف الزخم الهابط")

    # Bullish engulfing
    if is_c2_red and is_c3_green and (o3 < cl2) and (cl3 > o2):
        score += 2
        patterns.append("🔥 ابتلاع شرائي - سيطرة مشترين")

    return score, patterns


# =========================================================
# 📌 Pivot Points (existing) — keep signature
# =========================================================
def _pivot_points(series, left=3, right=3, mode="high"):
    if series is None or len(series) < left + right + 3:
        return []
    pivots = []
    arr = np.array(series.values, dtype=float)
    for i in range(left, len(arr) - right):
        window = arr[i - left: i + right + 1]
        if mode == "high":
            if arr[i] == np.max(window):
                pivots.append((i, float(arr[i])))
        else:
            if arr[i] == np.min(window):
                pivots.append((i, float(arr[i])))
    return pivots


# =========================================================
# 🧭 Market Structure + OTE (existing) — safer + clearer
# =========================================================
def _analyze_market_structure(df):
    if df is None or len(df) < 60 or not _has_ohlcv(df):
        return 0, []

    score = 0
    obs = []

    close = _col(df, "Close")
    high = _col(df, "High")
    low = _col(df, "Low")
    if close is None or high is None or low is None:
        return 0, []

    curr = float(close.iloc[-1])
    if curr <= 0:
        return 0, []

    ph = _pivot_points(high, 3, 3, "high")
    pl = _pivot_points(low, 3, 3, "low")

    # Swing reference
    try:
        last_swing_high = ph[-1][1] if ph else float(high.iloc[-25:-2].max())
        last_swing_low = pl[-1][1] if pl else float(low.iloc[-25:-2].min())
    except Exception:
        return 0, []

    if curr > last_swing_high:
        score += 3
        obs.append(f"🚀 BMS: كسر قمة سوينغ ({last_swing_high:.2f})")
    elif curr < last_swing_low:
        score -= 3
        obs.append(f"⚠️ BMS: كسر قاع سوينغ ({last_swing_low:.2f})")
    else:
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

    # ✅ OTE fix (keep your logic but safer)
    try:
        if len(ph) >= 1 and len(pl) >= 1:
            last_high_i, last_high = ph[-1]
            last_low_i, last_low = pl[-1]

            near_th = 0.01

            # موجة صاعدة
            if last_low_i < last_high_i:
                impulse_low = float(last_low)
                impulse_high = float(last_high)
                fib50 = impulse_low + 0.5 * (impulse_high - impulse_low)

                if abs(curr - fib50) / max(curr, 1e-9) < near_th:
                    score += 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة دخول أفضل)")

            # موجة هابطة
            else:
                impulse_high = float(last_high)
                impulse_low = float(last_low)
                fib50 = impulse_high - 0.5 * (impulse_high - impulse_low)

                if abs(curr - fib50) / max(curr, 1e-9) < near_th:
                    score -= 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة بيع أفضل)")
    except Exception:
        pass

    return score, obs


# =========================================================
# 🧲 Liquidity Sweep (existing) — safer
# =========================================================
def _detect_liquidity_sweep(df, lookback=30):
    if df is None or len(df) < lookback + 5 or not _has_ohlcv(df):
        return 0, [], {}

    score = 0
    obs = []
    feats = {"liq_sweep_high": 0, "liq_sweep_low": 0}

    recent = df.iloc[-(lookback + 1):-1]
    prev_high = _sf(recent["High"].max(), 0.0)
    prev_low = _sf(recent["Low"].min(), 0.0)

    last = df.iloc[-1]
    h = _sf(last["High"])
    l = _sf(last["Low"])
    c = _sf(last["Close"])

    if prev_high > 0 and h > prev_high and c < prev_high:
        score -= 2
        feats["liq_sweep_high"] = 1
        obs.append("🧲 صيد سيولة شرائية (اختراق زائف للأعلى)")

    if prev_low > 0 and l < prev_low and c > prev_low:
        score += 2
        feats["liq_sweep_low"] = 1
        obs.append("🧲 صيد سيولة بيعية (اختراق زائف للأسفل)")

    return score, obs, feats


# =========================================================
# 🧱 Order Block (existing) — safer + less false positives
# =========================================================
def _detect_order_block(df):
    if df is None or len(df) < 80 or not _has_ohlcv(df):
        return 0, [], {}

    score = 0
    obs = []
    feats = {"bull_ob_retest": 0, "bear_ob_retest": 0}

    close = _col(df, "Close")
    high = _col(df, "High")
    low = _col(df, "Low")
    open_ = _col(df, "Open")
    if any(x is None for x in [close, high, low, open_]):
        return 0, [], feats

    rng = (high - low).abs()
    avg_rng = float(rng.iloc[-40:].mean()) if len(rng) >= 40 else float(rng.mean())
    if avg_rng <= 0:
        return 0, [], feats

    window = df.iloc[-25:].copy()
    w_high = _col(window, "High")
    w_low = _col(window, "Low")
    w_close = _col(window, "Close")
    w_open = _col(window, "Open")

    # impulse up candle
    idx_impulse_up = None
    for i in range(len(window) - 1, 1, -1):
        r = float(w_high.iloc[i] - w_low.iloc[i])
        if r > avg_rng * 1.4 and float(w_close.iloc[i]) > float(w_open.iloc[i]):
            idx_impulse_up = window.index[i]
            break

    if idx_impulse_up is not None:
        sub = df.loc[:idx_impulse_up].tail(15)
        bears = sub[sub["Close"] < sub["Open"]]
        if not bears.empty:
            ob_idx = bears.index[-1]
            ob_low = float(low.loc[ob_idx])
            ob_high = float(high.loc[ob_idx])
            last_c = float(close.iloc[-1])
            last_l = float(low.iloc[-1])

            # retest: wick inside zone + close respected
            if (last_l <= ob_high) and (last_c >= ob_low):
                score += 2
                feats["bull_ob_retest"] = 1
                obs.append("🧱 Bullish Order Block retest (منطقة شراء محتملة)")

    # impulse down candle
    idx_impulse_dn = None
    for i in range(len(window) - 1, 1, -1):
        r = float(w_high.iloc[i] - w_low.iloc[i])
        if r > avg_rng * 1.4 and float(w_close.iloc[i]) < float(w_open.iloc[i]):
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


# =========================================================
# ☁️ Ichimoku (existing) — safer
# =========================================================
def _ichimoku(df):
    high = _col(df, "High")
    low = _col(df, "Low")
    close = _col(df, "Close")

    tenkan = (high.rolling(9).max() + low.rolling(9).min()) / 2
    kijun = (high.rolling(26).max() + low.rolling(26).min()) / 2
    span_a = ((tenkan + kijun) / 2).shift(26)
    span_b = ((high.rolling(52).max() + low.rolling(52).min()) / 2).shift(26)
    chikou = close.shift(-26)
    return tenkan, kijun, span_a, span_b, chikou


def _analyze_ichimoku(df):
    if df is None or len(df) < 120 or not _has_ohlcv(df):
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
    close = _col(df, "Close")

    c = float(close.iloc[-1])
    sa = float(span_a.iloc[-1]) if pd.notna(span_a.iloc[-1]) else np.nan
    sb = float(span_b.iloc[-1]) if pd.notna(span_b.iloc[-1]) else np.nan
    if np.isnan(sa) or np.isnan(sb):
        return 0, [], feats

    cloud_top = max(sa, sb)
    cloud_bot = min(sa, sb)

    try:
        chik = float(chikou.iloc[-27])
        price_26 = float(close.iloc[-27])
    except Exception:
        chik = None
        price_26 = None

    if c > cloud_top:
        score += 1
        obs.append("☁️ السعر فوق سحابة الكومو (Bias شرائي)")
    elif c < cloud_bot:
        score -= 1
        obs.append("☁️ السعر تحت سحابة الكومو (Bias بيعي)")
    else:
        obs.append("☁️ السعر داخل السحابة (تذبذب/ضعف ترند)")

    # TK Cross
    try:
        if float(tenkan.iloc[-1]) > float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) <= float(kijun.iloc[-2]):
            score += 1
            feats["ichi_tk_cross_up"] = 1
            obs.append("🔀 تقاطع تنكن فوق كيجن (إشارة دعم للشراء)")
        if float(tenkan.iloc[-1]) < float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) >= float(kijun.iloc[-2]):
            score -= 1
            feats["ichi_tk_cross_dn"] = 1
            obs.append("🔀 تقاطع تنكن تحت كيجن (إشارة دعم للبيع)")
    except Exception:
        pass

    # Strong Ichimoku
    try:
        if (c > cloud_top) and (float(span_a.iloc[-1]) > float(span_b.iloc[-1])) and (chik is not None) and (price_26 is not None) and (chik > price_26):
            score += 2
            feats["ichi_bull"] = 1
            obs.append("✅ Ichimoku صاعد قوي (شينكو+سحابة+سعر)")

        if (c < cloud_bot) and (float(span_a.iloc[-1]) < float(span_b.iloc[-1])) and (chik is not None) and (price_26 is not None) and (chik < price_26):
            score -= 2
            feats["ichi_bear"] = 1
            obs.append("⛔ Ichimoku هابط قوي (شينكو+سحابة+سعر)")
    except Exception:
        pass

    return score, obs, feats


# =========================================================
# 💰 Financial Golden Rules (existing) — keep outputs
# =========================================================
def _analyze_financial_golden_rules(symbol):
    try:
        from financial_analysis import get_advanced_fundamental_ratios
        metrics = get_advanced_fundamental_ratios(symbol)
        if not isinstance(metrics, dict):
            metrics = {}
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

    metrics["_fund_features"] = feats
    return score, obs, metrics


# =========================================================
# ✅ إضافات: أفكار اتفقنا عليها (بدون كسر)
# =========================================================
def _detect_inside_bar(df, lookback=3):
    """
    Inside Bar: شمعة اليوم داخل مدى أمس
    مفيد للتجميع/الاختراق
    """
    if df is None or len(df) < max(lookback, 3) or not _has_ohlcv(df):
        return 0, [], {"inside_bar": 0}

    score = 0
    obs = []
    feats = {"inside_bar": 0}

    prev = df.iloc[-2]
    last = df.iloc[-1]

    ph = _sf(prev["High"])
    pl = _sf(prev["Low"])
    lh = _sf(last["High"])
    ll = _sf(last["Low"])

    if (lh <= ph) and (ll >= pl):
        feats["inside_bar"] = 1
        score += 1
        obs.append("📦 Inside Bar (ضغط/تجميع) — ترقّب كسر النطاق")

    return score, obs, feats


def _detect_gaps(df, min_gap_pct=0.012):
    """
    Gap detection (بسيط):
    - Gap Up: افتتاح فوق قمة أمس بنسبة معينة
    - Gap Down: افتتاح تحت قاع أمس
    """
    if df is None or len(df) < 5 or not _has_ohlcv(df):
        return 0, [], {"gap_up": 0, "gap_down": 0}

    score = 0
    obs = []
    feats = {"gap_up": 0, "gap_down": 0}

    prev = df.iloc[-2]
    last = df.iloc[-1]

    prev_h = _sf(prev["High"])
    prev_l = _sf(prev["Low"])
    o = _sf(last["Open"])
    c = _sf(last["Close"])

    if prev_h > 0 and o > prev_h * (1 + min_gap_pct):
        feats["gap_up"] = 1
        score += 1
        obs.append("🕳️ Gap Up (فجوة صاعدة) — قوة/اندفاع (تحقق من الاستمرارية)")
        # لو أغلق داخل الفجوة = ضعف
        if c < prev_h:
            score -= 1
            obs.append("🧨 ردم فجوة صاعدة (إغلاق تحت قمة أمس) — ضعف محتمل")

    if prev_l > 0 and o < prev_l * (1 - min_gap_pct):
        feats["gap_down"] = 1
        score -= 1
        obs.append("🕳️ Gap Down (فجوة هابطة) — ضغط بيع (تحقق من الاسترداد)")
        if c > prev_l:
            score += 1
            obs.append("✅ استرداد فجوة هابطة (إغلاق فوق قاع أمس) — ارتداد محتمل")

    return score, obs, feats


def _detect_rsi_divergence(df, ind: dict, lookback=80):
    """
    Divergence RSI (مبسّط وقابل للتوسعة):
    - Bullish: سعر يصنع قاع أقل + RSI قاع أعلى
    - Bearish: سعر يصنع قمة أعلى + RSI قمة أقل
    يعتمد على pivots.
    """
    feats = {"rsi_bull_div": 0, "rsi_bear_div": 0}
    if df is None or df.empty or len(df) < max(lookback, 60) or not _has_ohlcv(df):
        return 0, [], feats

    rsi = ind.get("rsi14") if isinstance(ind, dict) else None
    if not isinstance(rsi, pd.Series) or rsi.empty:
        return 0, [], feats

    score = 0
    obs = []

    d = df.tail(lookback).copy()
    close = pd.to_numeric(d["Close"], errors="coerce").astype(float)
    r = rsi.reindex(d.index).astype(float)

    # pivots for price
    pl = _pivot_points(close, 3, 3, mode="low")
    ph = _pivot_points(close, 3, 3, mode="high")

    # Bullish divergence: last two lows
    try:
        if len(pl) >= 2:
            i1, p1 = pl[-2]
            i2, p2 = pl[-1]
            # map to rsi points (same index positions in tail array)
            r1 = float(r.iloc[i1])
            r2 = float(r.iloc[i2])
            if (p2 < p1) and (r2 > r1):
                feats["rsi_bull_div"] = 1
                score += 2
                obs.append("🟢 Divergence RSI إيجابي (قاع أدنى بالسعر + RSI أعلى)")

        # Bearish divergence: last two highs
        if len(ph) >= 2:
            j1, q1 = ph[-2]
            j2, q2 = ph[-1]
            rr1 = float(r.iloc[j1])
            rr2 = float(r.iloc[j2])
            if (q2 > q1) and (rr2 < rr1):
                feats["rsi_bear_div"] = 1
                score -= 2
                obs.append("🔴 Divergence RSI سلبي (قمة أعلى بالسعر + RSI أقل)")
    except Exception:
        pass

    return score, obs, feats


def _regime_hint_from_adx(ind: dict):
    """
    Hint بسيط:
    - ADX>=25 => Trending regime
    - ADX<20 => Range regime
    """
    feats = {"regime_trend": 0, "regime_range": 0}
    if not isinstance(ind, dict):
        return 0, [], feats

    adx = ind.get("adx14")
    if not isinstance(adx, pd.Series) or adx.empty or pd.isna(adx.iloc[-1]):
        return 0, [], feats

    score = 0
    obs = []
    v = float(adx.iloc[-1])

    if v >= 25:
        feats["regime_trend"] = 1
        score += 1
        obs.append("📈 Regime: ترند واضح (ADX مرتفع) — الاستراتيجيات الاتجاهية أفضل")
    elif v < 20:
        feats["regime_range"] = 1
        score -= 1
        obs.append("📉 Regime: تذبذب/رينج (ADX منخفض) — الارتدادات/الزونز أفضل")
    else:
        obs.append("📊 Regime: متوسط (ADX متوسط)")

    return score, obs, feats


def _vsa_lite(df, lookback=60):
    """
    VSA-lite (مبدئي داخل technicals قبل فصل vsa.py):
    - No Supply: سبريد صغير + فوليوم أقل من المتوسط + إغلاق أعلى منتصف الشمعة
    - No Demand: سبريد صغير + فوليوم أقل من المتوسط + إغلاق أقل منتصف الشمعة
    - Climactic volume: فوليوم عالي جدًا مع سبريد كبير
    """
    feats = {"vsa_no_supply": 0, "vsa_no_demand": 0, "vsa_climax": 0}
    if df is None or df.empty or len(df) < max(lookback, 30) or not _has_ohlcv(df):
        return 0, [], feats

    if "Volume" not in df.columns:
        return 0, [], feats

    score = 0
    obs = []

    d = df.tail(lookback).copy()
    high = pd.to_numeric(d["High"], errors="coerce").astype(float)
    low = pd.to_numeric(d["Low"], errors="coerce").astype(float)
    close = pd.to_numeric(d["Close"], errors="coerce").astype(float)
    vol = pd.to_numeric(d["Volume"], errors="coerce").fillna(0).astype(float)

    spread = (high - low).abs()
    avg_spread = float(spread.iloc[-30:].mean()) if len(spread) >= 30 else float(spread.mean())
    avg_vol = float(vol.iloc[-30:].mean()) if len(vol) >= 30 else float(vol.mean())

    if avg_spread <= 0 or avg_vol <= 0:
        return 0, [], feats

    # last candle
    h = float(high.iloc[-1])
    l = float(low.iloc[-1])
    c = float(close.iloc[-1])
    v = float(vol.iloc[-1])
    sp = float(spread.iloc[-1])
    mid = l + 0.5 * (h - l)

    # No Supply
    if (sp < avg_spread * 0.7) and (v < avg_vol * 0.7) and (c >= mid):
        feats["vsa_no_supply"] = 1
        score += 1
        obs.append("🟩 VSA: No Supply (عرض قليل/فوليوم ضعيف) — احتمال توقف بيع")

    # No Demand
    if (sp < avg_spread * 0.7) and (v < avg_vol * 0.7) and (c <= mid):
        feats["vsa_no_demand"] = 1
        score -= 1
        obs.append("🟥 VSA: No Demand (طلب ضعيف) — حذر استمرار ضعف")

    # Climax
    if (v > avg_vol * 2.2) and (sp > avg_spread * 1.6):
        feats["vsa_climax"] = 1
        # اتجاه الإغلاق يعطي دلالة
        if c >= mid:
            score += 1
            obs.append("🌋 VSA: Climactic Volume (ذروة مع إغلاق قوي) — احتمال نهاية هبوط/انعكاس")
        else:
            score -= 1
            obs.append("🌋 VSA: Climactic Volume (ذروة مع إغلاق ضعيف) — احتمال توزيع/نهاية صعود")

    return score, obs, feats
