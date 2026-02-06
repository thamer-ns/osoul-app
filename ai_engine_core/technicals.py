from osoli_logging import log_exception
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


def _safe_pct(a, b, default=0.0):
    try:
        a = float(a)
        b = float(b)
        if b == 0:
            return default
        return (a - b) / abs(b)
    except Exception:
        return default


def _clip01(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except Exception:
        return 0.0


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
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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

        # ✅ NEW (اختياري): دمج flags إذا metrics.py صار يرجعها
        try:
            fflags = metrics.get("_fund_flags") or {}
            # (لا نغيّر سكور هنا كثير — نضيف Observations فقط)
            if int(fflags.get("fund_high_leverage") or 0) == 1:
                obs.append("⚠️ التزامات مرتفعة (Leverage high)")
            if int(fflags.get("fund_altman_low") or 0) == 1:
                obs.append("⛔ Altman Z منخفض (مخاطر أعلى)")
            if int(fflags.get("fund_low_liquidity") or 0) == 1:
                obs.append("⚠️ سيولة ضعيفة (Current Ratio منخفض)")
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    metrics["_fund_features"] = feats
    return score, obs, metrics


# =========================================================
# ✅ إضافات: أفكار اتفقنا عليها (بدون كسر) — موجودة عندك
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

    pl = _pivot_points(close, 3, 3, mode="low")
    ph = _pivot_points(close, 3, 3, mode="high")

    try:
        if len(pl) >= 2:
            i1, p1 = pl[-2]
            i2, p2 = pl[-1]
            r1 = float(r.iloc[i1])
            r2 = float(r.iloc[i2])
            if (p2 < p1) and (r2 > r1):
                feats["rsi_bull_div"] = 1
                score += 2
                obs.append("🟢 Divergence RSI إيجابي (قاع أدنى بالسعر + RSI أعلى)")

        if len(ph) >= 2:
            j1, q1 = ph[-2]
            j2, q2 = ph[-1]
            rr1 = float(r.iloc[j1])
            rr2 = float(r.iloc[j2])
            if (q2 > q1) and (rr2 < rr1):
                feats["rsi_bear_div"] = 1
                score -= 2
                obs.append("🔴 Divergence RSI سلبي (قمة أعلى بالسعر + RSI أقل)")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
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

    h = float(high.iloc[-1])
    l = float(low.iloc[-1])
    c = float(close.iloc[-1])
    v = float(vol.iloc[-1])
    sp = float(spread.iloc[-1])
    mid = l + 0.5 * (h - l)

    if (sp < avg_spread * 0.7) and (v < avg_vol * 0.7) and (c >= mid):
        feats["vsa_no_supply"] = 1
        score += 1
        obs.append("🟩 VSA: No Supply (عرض قليل/فوليوم ضعيف) — احتمال توقف بيع")

    if (sp < avg_spread * 0.7) and (v < avg_vol * 0.7) and (c <= mid):
        feats["vsa_no_demand"] = 1
        score -= 1
        obs.append("🟥 VSA: No Demand (طلب ضعيف) — حذر استمرار ضعف")

    if (v > avg_vol * 2.2) and (sp > avg_spread * 1.6):
        feats["vsa_climax"] = 1
        if c >= mid:
            score += 1
            obs.append("🌋 VSA: Climactic Volume (ذروة مع إغلاق قوي) — احتمال نهاية هبوط/انعكاس")
        else:
            score -= 1
            obs.append("🌋 VSA: Climactic Volume (ذروة مع إغلاق ضعيف) — احتمال توزيع/نهاية صعود")

    return score, obs, feats


# =========================================================
# ✅ إضافات جديدة: مؤشرات/متوسطات/زخم/تأكيد حجم
# =========================================================
def _analyze_ma_trend(ind: dict):
    """
    MA 50/200 + Golden/Death Cross + Price bias (يدخل عبر features)
    """
    feats = {
        "ma_price_above_50": 0,
        "ma_price_above_200": 0,
        "golden_cross": 0,
        "death_cross": 0,
    }
    if not isinstance(ind, dict):
        return 0, [], feats

    sma50 = ind.get("sma50")
    sma200 = ind.get("sma200")
    close = ind.get("_close_series")  # optional hook if provided

    if not isinstance(sma50, pd.Series) or sma50.empty:
        return 0, [], feats

    score = 0
    obs = []

    try:
        s50 = float(sma50.iloc[-1])
    except Exception:
        s50 = None

    try:
        s200 = float(sma200.iloc[-1]) if isinstance(sma200, pd.Series) and not pd.isna(sma200.iloc[-1]) else None
    except Exception:
        s200 = None

    c = None
    if isinstance(close, pd.Series) and not close.empty:
        try:
            c = float(close.iloc[-1])
        except Exception:
            c = None

    if c is not None and s50 is not None and s50 > 0:
        if c >= s50:
            feats["ma_price_above_50"] = 1
            score += 1
            obs.append("📈 السعر فوق MA50 (زخم إيجابي)")
        else:
            score -= 1
            obs.append("📉 السعر تحت MA50 (ضغط سلبي)")

    if c is not None and s200 is not None and s200 > 0:
        if c >= s200:
            feats["ma_price_above_200"] = 1
            score += 1
            obs.append("🏗️ السعر فوق MA200 (اتجاه طويل إيجابي)")
        else:
            score -= 1
            obs.append("🏚️ السعر تحت MA200 (اتجاه طويل سلبي)")

    # Golden/Death cross
    try:
        if s200 is not None and isinstance(sma50, pd.Series) and isinstance(sma200, pd.Series) and len(sma50) >= 3 and len(sma200) >= 3:
            prev = float(sma50.iloc[-2] - sma200.iloc[-2])
            now = float(sma50.iloc[-1] - sma200.iloc[-1])

            if prev <= 0 and now > 0:
                feats["golden_cross"] = 1
                score += 2
                obs.append("✨ Golden Cross (MA50 اخترق MA200 للأعلى)")
            if prev >= 0 and now < 0:
                feats["death_cross"] = 1
                score -= 2
                obs.append("☠️ Death Cross (MA50 كسر MA200 للأسفل)")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return score, obs, feats


def _analyze_momentum_signals(ind: dict):
    """
    RSI/MACD/Stoch إشارات بسيطة:
    - RSI overbought/oversold
    - MACD cross
    - Stoch cross
    """
    feats = {
        "rsi_overbought": 0,
        "rsi_oversold": 0,
        "macd_cross_up": 0,
        "macd_cross_dn": 0,
        "stoch_cross_up": 0,
        "stoch_cross_dn": 0,
    }
    if not isinstance(ind, dict):
        return 0, [], feats

    score = 0
    obs = []

    # RSI
    rsi = ind.get("rsi14")
    if isinstance(rsi, pd.Series) and len(rsi) >= 2 and not pd.isna(rsi.iloc[-1]):
        v = float(rsi.iloc[-1])
        if v >= 70:
            feats["rsi_overbought"] = 1
            score -= 1
            obs.append("🔥 RSI تشبع شرائي (حذر جني أرباح)")
        elif v <= 30:
            feats["rsi_oversold"] = 1
            score += 1
            obs.append("🧊 RSI تشبع بيعي (ارتداد محتمل)")

    # MACD cross
    macd = ind.get("macd")
    sig = ind.get("macd_signal")
    if isinstance(macd, pd.Series) and isinstance(sig, pd.Series) and len(macd) >= 2 and len(sig) >= 2:
        try:
            prev = float(macd.iloc[-2] - sig.iloc[-2])
            now = float(macd.iloc[-1] - sig.iloc[-1])
            if prev <= 0 and now > 0:
                feats["macd_cross_up"] = 1
                score += 1
                obs.append("🔀 MACD تقاطع صاعد (إشارة دعم للشراء)")
            if prev >= 0 and now < 0:
                feats["macd_cross_dn"] = 1
                score -= 1
                obs.append("🔀 MACD تقاطع هابط (إشارة دعم للبيع)")
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
    # Stoch cross
    k = ind.get("stoch_k")
    d = ind.get("stoch_d")
    if isinstance(k, pd.Series) and isinstance(d, pd.Series) and len(k) >= 2 and len(d) >= 2:
        try:
            prev = float(k.iloc[-2] - d.iloc[-2])
            now = float(k.iloc[-1] - d.iloc[-1])
            if prev <= 0 and now > 0:
                feats["stoch_cross_up"] = 1
                score += 1
                obs.append("🎛️ Stochastic تقاطع صاعد")
            if prev >= 0 and now < 0:
                feats["stoch_cross_dn"] = 1
                score -= 1
                obs.append("🎛️ Stochastic تقاطع هابط")
        except Exception as e:
            log_exception(e, "Ignored exception", level="DEBUG")
    return score, obs, feats


def _volume_confirm(df, lookback=30):
    """
    Volume confirmation:
    - spike if volume > avg * 1.8
    """
    feats = {"vol_spike": 0}
    if df is None or df.empty or len(df) < max(lookback, 25) or not _has_ohlcv(df):
        return 0, [], feats

    if "Volume" not in df.columns:
        return 0, [], feats

    score = 0
    obs = []

    v = pd.to_numeric(df["Volume"], errors="coerce").fillna(0).astype(float)
    avg = float(v.tail(lookback).mean()) if len(v) >= lookback else float(v.mean())
    last = float(v.iloc[-1])

    if avg > 0 and last > avg * 1.8:
        feats["vol_spike"] = 1
        score += 1
        obs.append("📣 حجم تداول مرتفع (تأكيد حركة/اختراق محتمل)")

    return score, obs, feats


def _detect_double_top_bottom(df, lookback=180, tol=0.015):
    """
    Double Top / Bottom مبسط:
    - يستخدم pivots على Close
    - قمتين متقاربتين + فشل الاختراق => سلبي
    - قاعين متقاربين + فشل الكسر => إيجابي
    """
    feats = {"double_top": 0, "double_bottom": 0}
    if df is None or df.empty or len(df) < max(lookback, 80) or not _has_ohlcv(df):
        return 0, [], feats

    score = 0
    obs = []

    d = df.tail(lookback).copy()
    close = pd.to_numeric(d["Close"], errors="coerce").astype(float)
    if close.isna().all():
        return 0, [], feats

    ph = _pivot_points(close, 4, 4, "high")
    pl = _pivot_points(close, 4, 4, "low")

    try:
        c = float(close.iloc[-1])
    except Exception:
        c = None

    # Double Top
    try:
        if len(ph) >= 2 and c is not None:
            (i1, h1), (i2, h2) = ph[-2], ph[-1]
            if h1 > 0 and abs(h2 - h1) / h1 <= tol:
                # failed breakout: close below the mid area
                mid = (h1 + h2) / 2.0
                if c < mid * (1 - 0.006):
                    feats["double_top"] = 1
                    score -= 2
                    obs.append("⛰️ Double Top (قمتين متقاربتين) — احتمال انعكاس سلبي")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    # Double Bottom
    try:
        if len(pl) >= 2 and c is not None:
            (j1, l1), (j2, l2) = pl[-2], pl[-1]
            if l1 > 0 and abs(l2 - l1) / l1 <= tol:
                mid = (l1 + l2) / 2.0
                if c > mid * (1 + 0.006):
                    feats["double_bottom"] = 1
                    score += 2
                    obs.append("🏞️ Double Bottom (قاعين متقاربين) — احتمال انعكاس إيجابي")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return score, obs, feats


def _analyze_relative_strength_vs_tasi(symbol: str):
    """
    Optional: uses market_data.get_relative_strength_vs_tasi
    """
    feats = {"rs_strong_vs_tasi": 0, "rs_weak_vs_tasi": 0}
    score = 0
    obs = []

    try:
        from market_data import get_relative_strength_vs_tasi
    except Exception:
        return 0, [], feats

    try:
        rs = get_relative_strength_vs_tasi(symbol, period=None, interval="1d") or {}
        if not rs.get("ok"):
            return 0, [], feats

        label = str(rs.get("label") or "")
        out_3m = _sf(rs.get("outperf_3m"), 0.0)
        out_1m = _sf(rs.get("outperf_1m"), 0.0)

        if ("أقوى" in label) or (out_3m > 0.05 and out_1m > 0):
            feats["rs_strong_vs_tasi"] = 1
            score += 1
            obs.append("📌 السهم أقوى من تاسي (Relative Strength إيجابي)")
        elif ("أضعف" in label) or (out_3m < -0.05 and out_1m < 0):
            feats["rs_weak_vs_tasi"] = 1
            score -= 1
            obs.append("📌 السهم أضعف من تاسي (Relative Strength سلبي)")
        else:
            obs.append("📌 Relative Strength محايد مقابل تاسي")

    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    return score, obs, feats

# =========================================================
# 🧠 Smart Money / Fibonacci / Patterns / Scalping (NEW)
# =========================================================

def _linreg_slope(y: np.ndarray) -> float:
    """Simple slope for pattern detection (safe)."""
    try:
        if y is None or len(y) < 5:
            return 0.0
        x = np.arange(len(y), dtype=float)
        y = np.asarray(y, dtype=float)
        x = x - x.mean()
        y = y - y.mean()
        den = float((x * x).sum())
        if den <= 0:
            return 0.0
        return float((x * y).sum() / den)
    except Exception:
        return 0.0


def _last_swing_from_pivots(df: pd.DataFrame, lookback: int = 220):
    """Return (low_i, low, high_i, high, direction) where direction in {'up','down','unknown'}.

    Uses pivots on High/Low for better SMC consistency.
    """
    if df is None or df.empty or len(df) < 80 or not _has_ohlcv(df):
        return None

    d = df.tail(lookback).copy()
    high = _col(d, "High")
    low = _col(d, "Low")
    if high is None or low is None:
        return None

    ph = _pivot_points(high, 3, 3, "high")
    pl = _pivot_points(low, 3, 3, "low")
    if not ph or not pl:
        return None

    # pick last swing pair by last pivot ordering
    hi_i, hi = ph[-1]
    lo_i, lo = pl[-1]
    direction = "unknown"

    # If last low happened before last high => last impulse up
    if lo_i < hi_i:
        direction = "up"
        low_i, low_v = lo_i, float(lo)
        high_i, high_v = hi_i, float(hi)
    else:
        direction = "down"
        # in down impulse, last high pivot is before last low pivot (often)
        low_i, low_v = lo_i, float(lo)
        high_i, high_v = hi_i, float(hi)

    # sanity
    if low_v <= 0 or high_v <= 0 or abs(high_v - low_v) <= 0:
        return None

    return {
        "low_i": int(low_i),
        "low": float(low_v),
        "high_i": int(high_i),
        "high": float(high_v),
        "direction": direction,
        "lookback": int(lookback),
    }


def _analyze_fibonacci_smc(df: pd.DataFrame, lookback: int = 220, near_th: float = 0.012):
    """Fibonacci retracement + extensions (127/161/261...) based on last swing.

    - Retracement: 0.382/0.5/0.618/0.786
    - Extensions: 1.272/1.618/2.618 (targets after break)
    """
    feats = {
        "fib_near_382": 0,
        "fib_near_500": 0,
        "fib_near_618": 0,
        "fib_near_786": 0,
        "fib_ext_127": 0,
        "fib_ext_161": 0,
        "fib_ext_261": 0,
    }
    if df is None or df.empty or len(df) < 90 or not _has_ohlcv(df):
        return 0, [], feats

    close = _col(df, "Close")
    if close is None or pd.isna(close.iloc[-1]):
        return 0, [], feats

    swing = _last_swing_from_pivots(df, lookback=lookback)
    if not swing:
        return 0, [], feats

    c = float(close.iloc[-1])
    hi = float(swing["high"])
    lo = float(swing["low"])
    rng = hi - lo
    if rng <= 0:
        return 0, [], feats

    score = 0
    obs = []

    # retracements relative to impulse direction
    if swing["direction"] == "up":
        r382 = hi - 0.382 * rng
        r500 = hi - 0.5 * rng
        r618 = hi - 0.618 * rng
        r786 = hi - 0.786 * rng

        levels = [("38.2%", r382, "fib_near_382"), ("50%", r500, "fib_near_500"),
                  ("61.8%", r618, "fib_near_618"), ("78.6%", r786, "fib_near_786")]

        for name, lvl, fkey in levels:
            if abs(c - lvl) / max(c, 1e-9) <= near_th:
                feats[fkey] = 1
                score += 1
                obs.append(f"🧬 فيبو Retracement {name} قريب ({lvl:.2f}) — منطقة قرار/دخول أفضل")

        # OTE zone (0.618-0.786) gets extra weight
        if (min(r618, r786) - (near_th * c)) <= c <= (max(r618, r786) + (near_th * c)):
            score += 1
            obs.append("🎯 OTE (61.8%→78.6%) — منطقة دخول ذكية محتملة")

        # extensions (targets after breakout)
        ext127 = hi + 0.272 * rng
        ext161 = hi + 0.618 * rng
        ext261 = hi + 1.618 * rng
        ext_levels = [("127%", ext127, "fib_ext_127"), ("161.8%", ext161, "fib_ext_161"), ("261.8%", ext261, "fib_ext_261")]

        if c > hi * (1 + 0.002):
            # breakout context: mention nearest target
            for name, lvl, fkey in ext_levels:
                if abs(c - lvl) / max(c, 1e-9) <= near_th * 1.3:
                    feats[fkey] = 1
                    score += 1
                    obs.append(f"🎯 هدف فيبو Extension {name} قريب ({lvl:.2f}) بعد الاختراق")
                    break
            else:
                obs.append(f"🚀 بعد اختراق القمة: أهداف فيبو (127%={ext127:.2f} / 161.8%={ext161:.2f} / 261.8%={ext261:.2f})")

    else:
        # down impulse
        r382 = lo + 0.382 * rng
        r500 = lo + 0.5 * rng
        r618 = lo + 0.618 * rng
        r786 = lo + 0.786 * rng

        levels = [("38.2%", r382, "fib_near_382"), ("50%", r500, "fib_near_500"),
                  ("61.8%", r618, "fib_near_618"), ("78.6%", r786, "fib_near_786")]

        for name, lvl, fkey in levels:
            if abs(c - lvl) / max(c, 1e-9) <= near_th:
                feats[fkey] = 1
                score -= 1
                obs.append(f"🧬 فيبو Retracement {name} قريب ({lvl:.2f}) — منطقة قرار/بيع أفضل")

        if (min(r618, r786) - (near_th * c)) <= c <= (max(r618, r786) + (near_th * c)):
            score -= 1
            obs.append("🎯 OTE (61.8%→78.6%) — منطقة بيع ذكية محتملة")

        ext127 = lo - 0.272 * rng
        ext161 = lo - 0.618 * rng
        ext261 = lo - 1.618 * rng
        ext_levels = [("127%", ext127, "fib_ext_127"), ("161.8%", ext161, "fib_ext_161"), ("261.8%", ext261, "fib_ext_261")]

        if c < lo * (1 - 0.002):
            for name, lvl, fkey in ext_levels:
                if abs(c - lvl) / max(c, 1e-9) <= near_th * 1.3:
                    feats[fkey] = 1
                    score -= 1
                    obs.append(f"🎯 هدف فيبو Extension {name} قريب ({lvl:.2f}) بعد الكسر")
                    break
            else:
                obs.append(f"📉 بعد كسر القاع: أهداف فيبو (127%={ext127:.2f} / 161.8%={ext161:.2f} / 261.8%={ext261:.2f})")

    return score, obs, feats


def _detect_swing_failure_pattern(df: pd.DataFrame, lookback: int = 60, wick_th: float = 0.002):
    """Swing Failure Pattern (SFP/SMS-like) as a dedicated signal.

    - Bearish SFP: price takes previous swing high (wick), then closes back below that high.
    - Bullish SFP: price takes previous swing low (wick), then closes back above that low.
    """
    feats = {"sfp_bear": 0, "sfp_bull": 0}
    if df is None or df.empty or len(df) < max(lookback, 60) or not _has_ohlcv(df):
        return 0, [], feats

    d = df.tail(lookback).copy()
    high = _col(d, "High")
    low = _col(d, "Low")
    close = _col(d, "Close")
    open_ = _col(d, "Open")
    if any(x is None for x in [high, low, close, open_]):
        return 0, [], feats

    score = 0
    obs = []

    ph = _pivot_points(high, 3, 3, "high")
    pl = _pivot_points(low, 3, 3, "low")
    if not ph or not pl:
        return 0, [], feats

    last = d.iloc[-1]
    h = float(last["High"])
    l = float(last["Low"])
    c = float(last["Close"])
    o = float(last["Open"])

    swing_high = float(ph[-1][1])
    swing_low = float(pl[-1][1])

    # Bearish SFP: wick above swing high then close below it
    if swing_high > 0 and (h > swing_high * (1 + wick_th)) and (c < swing_high) and (c < o):
        feats["sfp_bear"] = 1
        score -= 2
        obs.append(f"🧨 SFP/SMS سلبي: سحب سيولة فوق ({swing_high:.2f}) ثم إغلاق تحته (انعكاس محتمل)")

    # Bullish SFP: wick below swing low then close above it
    if swing_low > 0 and (l < swing_low * (1 - wick_th)) and (c > swing_low) and (c > o):
        feats["sfp_bull"] = 1
        score += 2
        obs.append(f"🧨 SFP/SMS إيجابي: سحب سيولة تحت ({swing_low:.2f}) ثم إغلاق فوقه (انعكاس محتمل)")

    return score, obs, feats


def _detect_amd_cycle(df: pd.DataFrame, lookback: int = 120):
    """AMD (Accumulation → Manipulation → Distribution) heuristic.

    This is intentionally conservative to avoid overfitting:
    - Accumulation: tight range + low volatility for a window
    - Manipulation: recent liquidity sweep
    - Distribution: break of structure with volume confirmation
    """
    feats = {"amd_accum": 0, "amd_manip": 0, "amd_dist": 0}
    if df is None or df.empty or len(df) < max(lookback, 90) or not _has_ohlcv(df):
        return 0, [], feats

    if "Volume" not in df.columns:
        # still can detect accumulation/manip loosely
        pass

    d = df.tail(lookback).copy()
    high = _col(d, "High")
    low = _col(d, "Low")
    close = _col(d, "Close")
    if any(x is None for x in [high, low, close]):
        return 0, [], feats

    score = 0
    obs = []

    # Accumulation: narrow range + low std returns
    rng = float((high.tail(50).max() - low.tail(50).min()) / max(float(close.iloc[-1]), 1e-9))
    rets = close.pct_change().tail(50).replace([np.inf, -np.inf], np.nan).dropna()
    volat = float(rets.std()) if len(rets) >= 10 else 0.0

    if rng <= 0.06 and volat <= 0.012:
        feats["amd_accum"] = 1
        score += 1
        obs.append("📦 AMD: Accumulation محتملة (نطاق ضيق + تذبذب منخفض)")

    # Manipulation: liquidity sweep in last candle(s)
    s_liq, o_liq, f_liq = _detect_liquidity_sweep(d, lookback=30)
    if int((f_liq or {}).get("liq_sweep_high") or 0) == 1 or int((f_liq or {}).get("liq_sweep_low") or 0) == 1:
        feats["amd_manip"] = 1
        score += (1 if s_liq > 0 else -1)  # align with sweep direction
        obs += (o_liq or [])

    # Distribution: structure break + volume spike
    try:
        # quick volume spike
        v = pd.to_numeric(d.get("Volume", pd.Series(index=d.index, data=np.nan)), errors="coerce").fillna(0).astype(float)
        v_avg = float(v.tail(40).mean()) if len(v) >= 40 else float(v.mean() or 0)
        v_last = float(v.iloc[-1]) if len(v) else 0.0
        vol_spike = (v_avg > 0 and v_last > v_avg * 1.8)

        s_struct, o_struct = _analyze_market_structure(d)
        # distribution: after manipulation, BOS opposite with volume
        if feats["amd_manip"] == 1 and vol_spike and abs(s_struct) >= 2:
            feats["amd_dist"] = 1
            score += (1 if s_struct > 0 else -1)
            obs.append("📤 AMD: Distribution/Expansion (كسر هيكل + فوليوم عالي بعد سحب سيولة)")
            obs += (o_struct or [])[:2]
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")

    return score, obs, feats


def _detect_chart_patterns(df: pd.DataFrame, lookback: int = 90):
    """Basic chart patterns (triangle/flag/wedge) — minimal but useful.

    الهدف: إضافة تغطية من ملف (نماذج وأنماط الشارت) بدون مبالغة في false positives.
    """
    feats = {"pat_triangle": 0, "pat_flag_bull": 0, "pat_flag_bear": 0, "pat_wedge": 0}
    if df is None or df.empty or len(df) < max(lookback, 70) or not _has_ohlcv(df):
        return 0, [], feats

    d = df.tail(lookback).copy()
    high = _col(d, "High")
    low = _col(d, "Low")
    close = _col(d, "Close")
    if any(x is None for x in [high, low, close]):
        return 0, [], feats

    score = 0
    obs = []

    # Triangle / Wedge via slopes
    hh = np.asarray(high.tail(60).values, dtype=float)
    ll = np.asarray(low.tail(60).values, dtype=float)
    sh = _linreg_slope(hh)
    sl = _linreg_slope(ll)

    # Converging: highs down + lows up => triangle
    if sh < 0 and sl > 0 and abs(sh) > 0 and abs(sl) > 0:
        feats["pat_triangle"] = 1
        score += 1
        obs.append("🔺 نموذج مثلث (Consolidation) — راقب الكسر مع الحجم")

    # Wedge: both slopes same direction but converging magnitude (bullish falling wedge / bearish rising wedge)
    if sh < 0 and sl < 0 and abs(sh) < abs(sl) * 0.9:
        feats["pat_wedge"] = 1
        score += 1
        obs.append("🪓 Wedge هابط (Falling Wedge) — ارتداد/اختراق محتمل")
    if sh > 0 and sl > 0 and abs(sl) < abs(sh) * 0.9:
        feats["pat_wedge"] = 1
        score -= 1
        obs.append("🪓 Wedge صاعد (Rising Wedge) — ضعف/كسر محتمل")

    # Flags: impulse then consolidation
    try:
        c = close.astype(float)
        move = float((c.iloc[-1] - c.iloc[-25]) / max(c.iloc[-25], 1e-9))
        cons_rng = float((high.tail(12).max() - low.tail(12).min()) / max(float(c.iloc[-1]), 1e-9))
        if move > 0.08 and cons_rng < 0.03:
            feats["pat_flag_bull"] = 1
            score += 1
            obs.append("🏁 Bull Flag محتمل (اندفاع ثم تجميع ضيق) — اختراق متوقع")
        if move < -0.08 and cons_rng < 0.03:
            feats["pat_flag_bear"] = 1
            score -= 1
            obs.append("🏁 Bear Flag محتمل (هبوط قوي ثم تجميع ضيق) — كسر متوقع")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")

    return score, obs, feats


def _scalping_profile(df: pd.DataFrame, indicators: dict, ema_fast: int = 9, ema_slow: int = 21):
    """Scalping profile (ruleset) — independent from timeframe, works best on intraday.

    Signals are conservative and return hints, not absolute orders.
    """
    feats = {"scalp_long": 0, "scalp_short": 0}
    if df is None or df.empty or len(df) < 60 or not _has_ohlcv(df):
        return 0, [], feats

    close = _col(df, "Close")
    if close is None or close.isna().all():
        return 0, [], feats

    score = 0
    obs = []

    c = close.astype(float)
    ema_f = c.ewm(span=ema_fast, adjust=False).mean()
    ema_s = c.ewm(span=ema_slow, adjust=False).mean()

    rsi = indicators.get("rsi14") if isinstance(indicators, dict) else None
    adx = indicators.get("adx14") if isinstance(indicators, dict) else None

    try:
        cf = float(c.iloc[-1])
        ef = float(ema_f.iloc[-1])
        es = float(ema_s.iloc[-1])
    except Exception:
        return 0, [], feats

    rsi_v = None
    if isinstance(rsi, pd.Series) and len(rsi) >= 1 and not pd.isna(rsi.iloc[-1]):
        rsi_v = float(rsi.iloc[-1])

    adx_v = None
    if isinstance(adx, pd.Series) and len(adx) >= 1 and not pd.isna(adx.iloc[-1]):
        adx_v = float(adx.iloc[-1])

    trend_ok = (adx_v is None) or (adx_v >= 18)

    # pullback proximity
    near_fast = abs(cf - ef) / max(cf, 1e-9) <= 0.006

    if ef > es and trend_ok and near_fast and (rsi_v is None or 48 <= rsi_v <= 72):
        feats["scalp_long"] = 1
        score += 1
        obs.append("⚡ سكالبينج: Bias شراء (EMA9 فوق EMA21 + ارتداد قرب EMA9)")

    if ef < es and trend_ok and near_fast and (rsi_v is None or 28 <= rsi_v <= 52):
        feats["scalp_short"] = 1
        score -= 1
        obs.append("⚡ سكالبينج: Bias بيع (EMA9 تحت EMA21 + ارتداد قرب EMA9)")

    return score, obs, feats
