from osoli_logging import log_exception
# ai_engine_core/vsa.py
import numpy as np
import pandas as pd


def _sma(s: pd.Series, n: int):
    return s.rolling(n).mean()


def _safe_series(df, col, default=0.0):
    if df is None or df.empty or col not in df.columns:
        return pd.Series([], dtype=float)
    return pd.to_numeric(df[col], errors="coerce").fillna(default).astype(float)


def _body(open_, close):
    return (close - open_).abs()


def _spread(high, low):
    return (high - low).abs()


def _dir(close):
    d = np.sign(close.diff()).fillna(0.0)
    return d


def analyze_vsa(df: pd.DataFrame, lookback: int = 60):
    """
    VSA خفيف وعملي:
    - Effort vs Result (حجم عالي + نتيجة ضعيفة)
    - No Demand / No Supply
    - Stopping Volume / Climactic Volume
    - Upthrust / Shakeout
    - Absorption / Distribution (تقريبي عبر OBV slope + price response)
    """
    out = {
        "score": 0.0,
        "reasons": [],
        "features": {},
        "signals": [],
    }

    if df is None or df.empty or len(df) < max(lookback, 30):
        return out

    # Ensure columns
    for c in ["Open", "High", "Low", "Close"]:
        if c not in df.columns:
            return out

    open_ = _safe_series(df, "Open")
    high = _safe_series(df, "High")
    low = _safe_series(df, "Low")
    close = _safe_series(df, "Close")
    vol = _safe_series(df, "Volume", default=0.0)
    if len(vol) == 0:
        vol = pd.Series([0.0] * len(df), index=df.index)

    d = df.tail(int(lookback)).copy()
    open_ = open_.tail(int(lookback))
    high = high.tail(int(lookback))
    low = low.tail(int(lookback))
    close = close.tail(int(lookback))
    vol = vol.tail(int(lookback))

    # -------------------------
    # Data quality gate (Volume)
    # -------------------------
    try:
        zero_ratio = float((vol.fillna(0) <= 0).mean())
    except Exception:
        zero_ratio = 1.0
    out["features"]["vsa_zero_ratio"] = round(zero_ratio, 4)
    # إذا الحجم غير موثوق، عطّل VSA بدل إعطاء إشارات مضللة
    if zero_ratio > 0.35:
        out["features"]["vsa_data_quality"] = 0
        out["features"]["vsa_disabled"] = 1
        out["reasons"].append("⚠️ تم تعطيل VSA: بيانات الحجم (Volume) ضعيفة/صفرية بشكل ملحوظ.")
        return out
    out["features"]["vsa_data_quality"] = 1

    spread = _spread(high, low)
    body = _body(open_, close)
    up = close > open_
    down = close < open_

    vol_ma = _sma(vol, 20).bfill()
    spr_ma = _sma(spread.replace(0, np.nan), 20).bfill().fillna(spread.mean() if spread.mean() else 1.0)
    body_ma = _sma(body.replace(0, np.nan), 20).bfill().fillna(body.mean() if body.mean() else 1.0)

    # thresholds
    high_vol = vol > (1.6 * vol_ma)
    ultra_vol = vol > (2.2 * vol_ma)
    narrow_spread = spread < (0.75 * spr_ma)
    wide_spread = spread > (1.35 * spr_ma)
    small_body = body < (0.7 * body_ma)
    big_body = body > (1.35 * body_ma)

    # Candle position (close near high/low)
    rng = (high - low).replace(0, np.nan)
    close_pos = (close - low) / rng
    close_pos = close_pos.replace([np.inf, -np.inf], np.nan).fillna(0.5)

    # --- Signals (آخر 5 شموع للقرار + سياق) ---
    score = 0.0
    reasons = []
    feats = {}
    signals = []

    # 1) Effort vs Result (حجم عالي لكن spread ضيق/جسم صغير) = امتصاص / تلاعب
    evr = (high_vol & (narrow_spread | small_body))
    if evr.tail(5).any():
        score += 1.2
        reasons.append("🟣 VSA: Effort vs Result (حجم مرتفع مع نتيجة ضعيفة) → احتمال امتصاص/تجميع.")
        feats["vsa_evr"] = 1
        signals.append("EVR")

    # 2) No Demand: صعود + حجم ضعيف + spread ضيق
    no_demand = up & (vol < (0.85 * vol_ma)) & narrow_spread & (close_pos > 0.55)
    if no_demand.tail(5).any():
        score -= 1.0
        reasons.append("🟠 VSA: No Demand (صعود بحجم ضعيف) → ضعف طلب.")
        feats["vsa_no_demand"] = 1
        signals.append("NO_DEMAND")

    # 3) No Supply: هبوط + حجم ضعيف + spread ضيق
    no_supply = down & (vol < (0.85 * vol_ma)) & narrow_spread & (close_pos < 0.45)
    if no_supply.tail(5).any():
        score += 1.0
        reasons.append("🟢 VSA: No Supply (هبوط بحجم ضعيف) → ضعف عرض/جفاف بيع.")
        feats["vsa_no_supply"] = 1
        signals.append("NO_SUPPLY")

    # 4) Stopping Volume: هبوط + حجم عالي/فائق + إغلاق أعلى من منتصف الشمعة
    stopping = down & high_vol & (close_pos > 0.55)
    if stopping.tail(5).any():
        score += 1.4
        reasons.append("🟢 VSA: Stopping Volume (هبوط بحجم قوي وإغلاق جيد) → احتمال وقف هبوط/تجميع.")
        feats["vsa_stopping"] = 1
        signals.append("STOPPING_VOL")

    # 5) Climactic: حجم فائق + spread واسع (قمة/قاع محتمل)
    climactic = ultra_vol & wide_spread
    if climactic.tail(5).any():
        # اتجاه الإغلاق يحدد
        if (up & climactic).tail(5).any():
            score -= 1.3
            reasons.append("🔴 VSA: Climactic Up (حجم فائق + اتساع) → احتمال قمة/تصريف.")
            feats["vsa_climax_up"] = 1
            signals.append("CLIMAX_UP")
        if (down & climactic).tail(5).any():
            score += 1.3
            reasons.append("🟢 VSA: Climactic Down (حجم فائق + اتساع) → احتمال قاع/ذعر وارتداد.")
            feats["vsa_climax_down"] = 1
            signals.append("CLIMAX_DN")

    # 6) Upthrust: شمعة صاعدة بظل علوي كبير + إغلاق ضعيف قرب القاع + حجم عالي
    upper_wick = (high - close).clip(lower=0)
    wick_ratio = upper_wick / (rng.fillna(1.0))
    upthrust = up & high_vol & (wick_ratio > 0.45) & (close_pos < 0.45)
    if upthrust.tail(5).any():
        score -= 1.6
        reasons.append("🔴 VSA: Upthrust (فشل صعود مع ظل علوي وحجم قوي) → تصريف/فخ شراء.")
        feats["vsa_upthrust"] = 1
        signals.append("UPTHRUST")

    # 7) Shakeout: شمعة هابطة بذيل سفلي كبير + إغلاق قوي قرب القمة + حجم عالي
    lower_wick = (close - low).clip(lower=0)
    lw_ratio = lower_wick / (rng.fillna(1.0))
    shakeout = down & high_vol & (lw_ratio > 0.45) & (close_pos > 0.60)
    if shakeout.tail(5).any():
        score += 1.6
        reasons.append("🟢 VSA: Shakeout (هزّة بيع مع إغلاق قوي وحجم) → تجميع/فخ بيع.")
        feats["vsa_shakeout"] = 1
        signals.append("SHAKEOUT")

    # 8) Absorption/Distribution proxy via OBV slope + price response
    try:
        direction = np.sign(close.diff()).fillna(0.0)
        obv = (direction * vol).fillna(0.0).cumsum()
        obv_slope = obv.diff(5)
        price_slope = close.diff(5)

        # Absorption: OBV up بينما السعر flat/weak
        absorption = (obv_slope > 0) & (price_slope <= 0)
        if absorption.tail(10).any():
            score += 0.9
            reasons.append("🟣 VSA: Absorption (OBV يرتفع والسعر ضعيف) → امتصاص بيع محتمل.")
            feats["vsa_absorption"] = 1
            signals.append("ABSORPTION")

        # Distribution: OBV down بينما السعر flat/up
        distribution = (obv_slope < 0) & (price_slope >= 0)
        if distribution.tail(10).any():
            score -= 0.9
            reasons.append("🟠 VSA: Distribution (OBV يهبط والسعر متماسك/صاعد) → تصريف محتمل.")
            feats["vsa_distribution"] = 1
            signals.append("DISTRIBUTION")
    except Exception as e:
        log_exception(e, "Ignored exception", level="DEBUG")
    # clamp
    out["score"] = float(max(min(score, 6.0), -6.0))
    out["reasons"] = reasons[:12]
    out["features"] = feats
    out["signals"] = list(dict.fromkeys(signals))[:12]
    return out
