# ai_engine.py
# ============================================================
# 🤖 AI Engine (Advanced + Self-Learning Memory)
# - Candles + Market Structure + VSA + Fundamentals (existing)
# - NEW: Ichimoku, Supply/Demand Zones, BOS/CHOCH + OTE
# - NEW: Persistent Memory + Adaptive Weights (online learning)
# ============================================================

import json
import time
from datetime import datetime

import numpy as np
import pandas as pd

from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios

# ------------------------------------------------------------
# Optional DB (Fail-safe)
# ------------------------------------------------------------
DB_AVAILABLE = True
try:
    from database import execute_query, fetch_table
except Exception:
    DB_AVAILABLE = False
    execute_query = None
    fetch_table = None


# ============================================================
# Helpers
# ============================================================

def _now_iso():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


def _safe_float(x, default=0.0):
    try:
        if x is None:
            return default
        return float(x)
    except Exception:
        return default


def _ensure_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    need = ["Open", "High", "Low", "Close", "Volume"]
    for c in need:
        if c not in df.columns:
            return pd.DataFrame()
    out = df.copy()
    out = out.dropna(subset=["Open", "High", "Low", "Close"])
    return out


def _rolling_mid(high, low, n):
    return (high.rolling(n).max() + low.rolling(n).min()) / 2.0


# ============================================================
# 1) Advanced Candlestick Patterns (your base, preserved)
# ============================================================

def _detect_advanced_patterns(df):
    df = _ensure_ohlcv(df)
    if df.empty or len(df) < 5:
        return 0, []

    score = 0
    patterns = []

    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]

    body1 = abs(_safe_float(c1["Close"]) - _safe_float(c1["Open"]))
    body2 = abs(_safe_float(c2["Close"]) - _safe_float(c2["Open"]))
    body3 = abs(_safe_float(c3["Close"]) - _safe_float(c3["Open"]))

    is_c1_red = _safe_float(c1["Close"]) < _safe_float(c1["Open"])
    is_c1_green = _safe_float(c1["Close"]) > _safe_float(c1["Open"])
    is_c2_red = _safe_float(c2["Close"]) < _safe_float(c2["Open"])
    is_c2_green = _safe_float(c2["Close"]) > _safe_float(c2["Open"])
    is_c3_green = _safe_float(c3["Close"]) > _safe_float(c3["Open"])
    is_c3_red = _safe_float(c3["Close"]) < _safe_float(c3["Open"])

    # Morning Star
    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = _safe_float(c1["Open"]) - (body1 / 2)
        if _safe_float(c3["Close"]) > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح - انعكاس إيجابي قوي")

    # Evening Star
    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = _safe_float(c1["Open"]) + (body1 / 2)
        if _safe_float(c3["Close"]) < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء - انعكاس سلبي قوي")

    # Bullish Harami
    if is_c2_red and is_c3_green and _safe_float(c3["Open"]) > _safe_float(c2["Close"]) and _safe_float(c3["Close"]) < _safe_float(c2["Open"]):
        score += 2
        patterns.append("🤰 هارامي شرائي - ضعف الزخم الهابط")

    # Bullish Engulfing
    if is_c2_red and is_c3_green and _safe_float(c3["Open"]) < _safe_float(c2["Close"]) and _safe_float(c3["Close"]) > _safe_float(c2["Open"]):
        score += 2
        patterns.append("🔥 ابتلاع شرائي - سيطرة المشترين")

    # (Ready for extension) — you can add Doji/Hammer etc later safely.

    return score, patterns


# ============================================================
# 2) Market Structure (base preserved) + NEW: BOS/CHOCH + OTE
# ============================================================

def _find_swings(df, left=3, right=3):
    """Simple swing high/low detection."""
    if df is None or df.empty or len(df) < (left + right + 5):
        return [], []
    highs = df["High"].values
    lows = df["Low"].values
    swing_highs = []
    swing_lows = []
    for i in range(left, len(df) - right):
        if highs[i] == max(highs[i - left:i + right + 1]):
            swing_highs.append(i)
        if lows[i] == min(lows[i - left:i + right + 1]):
            swing_lows.append(i)
    return swing_highs, swing_lows


def _analyze_market_structure_basic(df):
    df = _ensure_ohlcv(df)
    if df.empty or len(df) < 30:
        return 0, []

    score = 0
    obs = []

    curr_price = _safe_float(df["Close"].iloc[-1])
    last_peak = _safe_float(df["High"].iloc[-25:-2].max())
    last_valley = _safe_float(df["Low"].iloc[-25:-2].min())

    if curr_price > last_peak:
        score += 3
        obs.append(f"🚀 اختراق قمة سابقة ({last_peak:.2f})")
    elif curr_price < last_valley:
        score -= 3
        obs.append(f"⚠️ كسر قاع سابق ({last_valley:.2f})")
    else:
        range_size = last_peak - last_valley
        if range_size > 0:
            pos = (curr_price - last_valley) / range_size
            if pos > 0.8:
                score += 1
                obs.append("السعر قريب من قمة النطاق (مراقبة)")
            elif pos < 0.2:
                score -= 1
                obs.append("السعر قريب من قاع النطاق (حذر)")
            else:
                score -= 1
                obs.append("مسار عرضي / تذبذب")

    return score, obs


def _analyze_bos_ote(df):
    """
    BOS(BMS) + OTE:
    - BOS: close above last swing high / below last swing low
    - OTE zone: retracement 0.50 .. 0.79 (approx) after impulse
    """
    df = _ensure_ohlcv(df)
    if df.empty or len(df) < 80:
        return 0, [], {}

    score = 0
    obs = []
    meta = {"bos": None, "ote_zone": None}

    swing_highs, swing_lows = _find_swings(df, left=3, right=3)
    if len(swing_highs) < 2 or len(swing_lows) < 2:
        return 0, [], meta

    close = df["Close"].values
    last_close = _safe_float(close[-1])

    # last swing points
    last_sh = swing_highs[-1]
    last_sl = swing_lows[-1]

    last_swing_high_price = _safe_float(df["High"].iloc[last_sh])
    last_swing_low_price = _safe_float(df["Low"].iloc[last_sl])

    # BOS check
    if last_close > last_swing_high_price:
        score += 3
        meta["bos"] = "bull"
        obs.append("🧱 BOS صاعد: إغلاق فوق آخر Swing High (انتظر إعادة اختبار)")
    elif last_close < last_swing_low_price:
        score -= 3
        meta["bos"] = "bear"
        obs.append("🧱 BOS هابط: إغلاق تحت آخر Swing Low (انتظر إعادة اختبار)")
    else:
        return 0, [], meta

    # Build impulse leg A->B for OTE
    # For bull: take last swing low before last_sh as A, B=last_sh
    # For bear: take last swing high before last_sl as A, B=last_sl
    if meta["bos"] == "bull":
        # find prior swing low index before last_sh
        prior_lows = [i for i in swing_lows if i < last_sh]
        if not prior_lows:
            return score, obs, meta
        A = prior_lows[-1]
        B = last_sh
        A_price = _safe_float(df["Low"].iloc[A])
        B_price = _safe_float(df["High"].iloc[B])
        if B_price <= A_price:
            return score, obs, meta

        # OTE retracement zone (0.50..0.79)
        r50 = B_price - 0.50 * (B_price - A_price)
        r79 = B_price - 0.79 * (B_price - A_price)
        zone_low = min(r50, r79)
        zone_high = max(r50, r79)
        meta["ote_zone"] = (zone_low, zone_high)

        if zone_low <= last_close <= zone_high:
            score += 2
            obs.append("🎯 السعر داخل OTE (50%-79%) — دخول منخفض المخاطر محتمل")
        else:
            obs.append("⌛ BOS موجود — راقب رجعة السعر لمنطقة OTE")

    else:  # bear
        prior_highs = [i for i in swing_highs if i < last_sl]
        if not prior_highs:
            return score, obs, meta
        A = prior_highs[-1]
        B = last_sl
        A_price = _safe_float(df["High"].iloc[A])
        B_price = _safe_float(df["Low"].iloc[B])
        if A_price <= B_price:
            return score, obs, meta

        r50 = B_price + 0.50 * (A_price - B_price)
        r79 = B_price + 0.79 * (A_price - B_price)
        zone_low = min(r50, r79)
        zone_high = max(r50, r79)
        meta["ote_zone"] = (zone_low, zone_high)

        if zone_low <= last_close <= zone_high:
            score -= 2
            obs.append("🎯 السعر داخل OTE (50%-79%) هابط — بيع منخفض المخاطر محتمل")
        else:
            obs.append("⌛ BOS هابط — راقب رجعة السعر لمنطقة OTE")

    return score, obs, meta


# ============================================================
# 3) Fundamentals Golden Rules (your base preserved)
# ============================================================

def _analyze_financial_golden_rules(symbol):
    try:
        metrics = get_advanced_fundamental_ratios(symbol)
    except Exception:
        return 0, [], {}

    score = 0
    obs = []

    try:
        piotroski = metrics.get("Piotroski_Score", 0)
        if piotroski >= 7:
            score += 3
            obs.append("💎 F-Score قوي (ملاءة/جودة أرباح)")
        elif piotroski <= 3:
            score -= 3
            obs.append("❌ F-Score ضعيف (هشاشة مالية)")

        fv = metrics.get("Fair_Value_Graham", 0)
        rating = metrics.get("Rating", "")
        if fv and fv > 0 and ("قوي" in str(rating) or "جيد" in str(rating)):
            score += 2
            obs.append("✅ تقييم جراهام/التصنيف إيجابي")

        ops_str = str(metrics.get("Opinions", ""))
        if ("سالب" in ops_str) and (("تشغيلي" in ops_str) or ("نقد" in ops_str)):
            score -= 4
            obs.append("⚠️ التدفق النقدي التشغيلي سلبي")
    except Exception:
        pass

    return score, obs, metrics


# ============================================================
# 4) VSA (your base preserved)
# ============================================================

def _analyze_vsa_art_of_trading(df):
    df = _ensure_ohlcv(df)
    if df.empty or len(df) < 20:
        return 0, []

    score = 0
    obs = []

    curr = df.iloc[-1]
    avg_vol = _safe_float(df["Volume"].iloc[-20:].mean())

    if _safe_float(curr["Volume"]) > avg_vol * 1.5 and avg_vol > 0:
        range_size = _safe_float(curr["High"] - curr["Low"])
        avg_range = _safe_float((df["High"] - df["Low"]).iloc[-20:].mean())
        if avg_range > 0 and range_size < avg_range * 0.8:
            obs.append("VSA: فوليوم عالي + مدى ضيق (احتمال امتصاص/تلاعب)")
            score -= 1

    return score, obs


# ============================================================
# 5) NEW: Ichimoku Module
# - Rules summarized from your Ichimoku PDF:
#   Trend up: Chikou فوق السعر + السعر فوق الكومو + (Tenkan فوق الكومو أفضل)
# ============================================================

def _ichimoku_calc(df, p_tenkan=9, p_kijun=26, p_senkou=52):
    df = _ensure_ohlcv(df)
    if df.empty or len(df) < (p_senkou + 5):
        return None

    high = df["High"]
    low = df["Low"]
    close = df["Close"]

    tenkan = _rolling_mid(high, low, p_tenkan)
    kijun = _rolling_mid(high, low, p_kijun)
    senkou_a = ((tenkan + kijun) / 2.0).shift(p_kijun)
    senkou_b = _rolling_mid(high, low, p_senkou).shift(p_kijun)
    chikou = close.shift(-p_kijun)

    out = df.copy()
    out["tenkan"] = tenkan
    out["kijun"] = kijun
    out["senkou_a"] = senkou_a
    out["senkou_b"] = senkou_b
    out["chikou"] = chikou
    return out


def _analyze_ichimoku(df):
    ichi = _ichimoku_calc(df)
    if ichi is None or ichi.empty:
        return 0, [], {}

    score = 0
    obs = []
    meta = {}

    last = ichi.iloc[-1]
    price = _safe_float(last["Close"])
    sen_a = _safe_float(last.get("senkou_a"))
    sen_b = _safe_float(last.get("senkou_b"))
    tenkan = _safe_float(last.get("tenkan"))
    kijun = _safe_float(last.get("kijun"))

    # Cloud boundaries
    cloud_top = max(sen_a, sen_b)
    cloud_bot = min(sen_a, sen_b)

    # Chikou compare: use shifted series carefully (if last chikou is nan, skip)
    chikou_val = last.get("chikou")
    chikou_ok = False
    if pd.notna(chikou_val):
        # compare chikou to price 26 periods back (approx)
        idx_back = -26
        if len(ichi) >= 30 and abs(idx_back) < len(ichi):
            price_back = _safe_float(ichi["Close"].iloc[idx_back])
            chikou_ok = _safe_float(chikou_val) > price_back

    # Trend
    if price > cloud_top and chikou_ok:
        score += 3
        obs.append("☁️ إيشيموكو صاعد: السعر فوق الكومو + الشينكو داعم")
        meta["trend"] = "bull"
    elif price < cloud_bot and pd.notna(chikou_val):
        # bearish chikou check
        idx_back = -26
        price_back = _safe_float(ichi["Close"].iloc[idx_back]) if len(ichi) >= 30 else price
        if _safe_float(chikou_val) < price_back:
            score -= 3
            obs.append("☁️ إيشيموكو هابط: السعر تحت الكومو + الشينكو سلبي")
            meta["trend"] = "bear"
    else:
        obs.append("☁️ إيشيموكو: السعر داخل/قريب من الكومو (تذبذب/حياد)")
        meta["trend"] = "range"
        score -= 1

    # Tenkan/Kijun momentum
    if tenkan > kijun and price >= tenkan:
        score += 1
        obs.append("⚡ تنكن فوق كيجن + السعر فوق تنكن (زخم إيجابي)")
    elif tenkan < kijun and price <= tenkan:
        score -= 1
        obs.append("⚡ تنكن تحت كيجن + السعر تحت تنكن (زخم سلبي)")

    meta["cloud"] = (cloud_bot, cloud_top)
    return score, obs, meta


# ============================================================
# 6) NEW: Supply & Demand Zones (lightweight + practical)
# - Detect base(تجميع) ثم impulse(اندفاع) => zone
# - "Fresh" zone: لم يتم لمسها بعد
# ============================================================

def _detect_supply_demand_zones(df, lookback=120):
    df = _ensure_ohlcv(df)
    if df.empty or len(df) < 60:
        return []

    d = df.tail(lookback).copy()
    d["range"] = (d["High"] - d["Low"]).replace(0, np.nan)
    d["body"] = (d["Close"] - d["Open"]).abs()
    avg_range = d["range"].rolling(20).mean()
    avg_vol = d["Volume"].rolling(20).mean()

    zones = []
    # scan for base -> impulse
    for i in range(25, len(d) - 5):
        base = d.iloc[i-4:i]  # 4-candle base
        imp = d.iloc[i:i+2]   # 2-candle impulse

        if base["range"].mean() < _safe_float(avg_range.iloc[i]) * 0.75 and base["body"].mean() < base["range"].mean() * 0.6:
            # impulse must be larger than average
            if imp["range"].mean() > _safe_float(avg_range.iloc[i]) * 1.35:
                # optional volume confirmation
                vol_ok = True
                if pd.notna(avg_vol.iloc[i]) and _safe_float(avg_vol.iloc[i]) > 0:
                    vol_ok = _safe_float(imp["Volume"].mean()) >= _safe_float(avg_vol.iloc[i]) * 1.10

                if not vol_ok:
                    continue

                # zone boundaries = base candle bodies/wicks
                z_high = _safe_float(base["High"].max())
                z_low = _safe_float(base["Low"].min())

                # direction by impulse close vs base
                direction = "demand" if _safe_float(imp["Close"].iloc[-1]) > _safe_float(base["Close"].iloc[-1]) else "supply"

                zones.append({
                    "type": direction,
                    "low": z_low,
                    "high": z_high,
                    "created_idx": d.index[i-1],
                })

    return zones[-6:]  # keep last zones


def _zone_is_fresh(df, zone, max_touches=0):
    """Fresh means price hasn't re-entered zone after creation."""
    df = _ensure_ohlcv(df)
    if df.empty:
        return False
    created = zone.get("created_idx")
    if created is None or created not in df.index:
        return True
    after = df.loc[created:].copy()
    if after.empty or len(after) < 5:
        return True

    lo, hi = zone["low"], zone["high"]
    touches = ((after["Low"] <= hi) & (after["High"] >= lo)).sum()
    return touches <= (1 + max_touches)  # first touch counts as 1


def _analyze_supply_demand(df):
    df = _ensure_ohlcv(df)
    if df.empty or len(df) < 80:
        return 0, [], {}

    zones = _detect_supply_demand_zones(df)
    if not zones:
        return 0, [], {"zones": []}

    price = _safe_float(df["Close"].iloc[-1])
    score = 0
    obs = []
    picked = None

    # pick nearest zone
    def dist(z):
        if z["low"] <= price <= z["high"]:
            return 0
        if price < z["low"]:
            return z["low"] - price
        return price - z["high"]

    zones_sorted = sorted(zones, key=dist)
    for z in zones_sorted:
        fresh = _zone_is_fresh(df, z, max_touches=0)
        z["fresh"] = fresh
    picked = zones_sorted[0]

    zlo, zhi = picked["low"], picked["high"]
    in_zone = (zlo <= price <= zhi)
    fresh = picked.get("fresh", False)

    if in_zone and picked["type"] == "demand":
        score += 2 if fresh else 1
        obs.append("🟩 داخل Demand Zone" + (" (Fresh)" if fresh else ""))
    elif in_zone and picked["type"] == "supply":
        score -= 2 if fresh else 1
        obs.append("🟥 داخل Supply Zone" + (" (Fresh)" if fresh else ""))

    # simple reaction check (last candle)
    last = df.iloc[-1]
    body = abs(_safe_float(last["Close"]) - _safe_float(last["Open"]))
    rng = _safe_float(last["High"] - last["Low"])
    if rng > 0:
        # rejection candle near zone
        if in_zone and body < rng * 0.45:
            obs.append("📌 شمعة رفض داخل المنطقة (احتمال ارتداد)")
            score += 1 if picked["type"] == "demand" else -1

    return score, obs, {"zones": zones, "picked": picked}


# ============================================================
# ✅ Confidence + Explainability (yours + improved)
# ============================================================

def _calc_confidence(tech_score, fund_score, df, agreement_bonus=0):
    quality = 0
    if df is not None and len(df) >= 160:
        quality += 30
    elif df is not None and len(df) >= 100:
        quality += 22
    elif df is not None and len(df) >= 60:
        quality += 15
    else:
        quality += 6

    strength = min(abs(tech_score + fund_score) * 7.5, 45)

    alignment = 25 if ((tech_score >= 0 and fund_score >= 0) or (tech_score <= 0 and fund_score <= 0)) else 10
    alignment += agreement_bonus

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

    pos_keys = [
        "اختراق", "BOS", "OTE", "نجمة", "ابتلاع", "سيطرة", "إشارة دخول",
        "قوية", "ملاءة", "عادل", "جيد", "✅", "💎", "Demand", "تنكن", "الكومو"
    ]

    for x in (tech_reasons or []):
        if any(k in x for k in pos_keys):
            positives.append(x)
        else:
            negatives.append(x)

    for x in (fund_reasons or []):
        if any(k in x for k in pos_keys):
            positives.append(x)
        else:
            negatives.append(x)

    notes.append(f"Tech Score = {tech_score} | Fund Score = {fund_score} | Total = {total_score}")

    if tech_score > 3 and fund_score < 0:
        notes.append("تعارض: الفني قوي لكن المالي ضعيف — الأفضل مضاربة بإدارة مخاطر.")
    if fund_score > 3 and tech_score < 0:
        notes.append("تعارض: المالي قوي لكن السعر ضعيف — مناسب لاستثمار قيمة بصبر.")

    return {"positives": positives[:12], "negatives": negatives[:12], "notes": notes[:12]}


# ============================================================
# 🧠 Learning Memory (DB)
# ============================================================

def _memory_init():
    if not DB_AVAILABLE:
        return
    try:
        # signals log
        execute_query("""
            CREATE TABLE IF NOT EXISTS ai_signals (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                timeframe TEXT,
                recommendation TEXT,
                strategy_tag TEXT,
                tech_score REAL,
                fund_score REAL,
                total_score REAL,
                confidence REAL,
                payload_json TEXT
            )
        """, tuple())

        # outcomes log (manual/backtest)
        execute_query("""
            CREATE TABLE IF NOT EXISTS ai_outcomes (
                id SERIAL PRIMARY KEY,
                ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                symbol TEXT,
                outcome_type TEXT,
                return_pct REAL,
                meta_json TEXT
            )
        """, tuple())

        # adaptive weights
        execute_query("""
            CREATE TABLE IF NOT EXISTS ai_weights (
                module TEXT PRIMARY KEY,
                weight REAL,
                updated_ts TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """, tuple())

        # seed defaults if missing
        defaults = {
            "candles": 1.0,
            "structure": 1.0,
            "bos_ote": 1.0,
            "ichimoku": 1.0,
            "supply_demand": 1.0,
            "vsa": 1.0,
            "fundamentals": 1.0,
        }
        for m, w in defaults.items():
            try:
                execute_query(
                    "INSERT INTO ai_weights (module, weight) VALUES (%s,%s) ON CONFLICT (module) DO NOTHING",
                    (m, w)
                )
            except Exception:
                pass

    except Exception:
        # if DB fails, just disable learning
        pass


def _get_weights():
    defaults = {
        "candles": 1.0,
        "structure": 1.0,
        "bos_ote": 1.0,
        "ichimoku": 1.0,
        "supply_demand": 1.0,
        "vsa": 1.0,
        "fundamentals": 1.0,
    }
    if not DB_AVAILABLE:
        return defaults

    try:
        df = fetch_table("ai_weights")
        if df is None or df.empty:
            return defaults
        out = defaults.copy()
        for _, r in df.iterrows():
            out[str(r["module"])] = _safe_float(r["weight"], out.get(str(r["module"]), 1.0))
        return out
    except Exception:
        return defaults


def _log_signal(symbol, timeframe, rep):
    if not DB_AVAILABLE:
        return
    try:
        payload = json.dumps(rep, ensure_ascii=False)
        execute_query(
            """INSERT INTO ai_signals (symbol, timeframe, recommendation, strategy_tag,
                                      tech_score, fund_score, total_score, confidence, payload_json)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                symbol,
                timeframe,
                str(rep.get("recommendation", "")),
                str(rep.get("strategy_tag", "")),
                _safe_float(rep.get("tech_score")),
                _safe_float(rep.get("fund_score")),
                _safe_float(rep.get("total_score")),
                _safe_float(rep.get("confidence")),
                payload
            )
        )
    except Exception:
        pass


def record_outcome(symbol, return_pct, outcome_type="backtest", meta=None):
    """
    Call this after a backtest or after closing a real trade.
    - outcome_type: 'backtest' or 'real_trade'
    """
    if not DB_AVAILABLE:
        return False
    try:
        m = json.dumps(meta or {}, ensure_ascii=False)
        execute_query(
            "INSERT INTO ai_outcomes (symbol, outcome_type, return_pct, meta_json) VALUES (%s,%s,%s,%s)",
            (symbol, outcome_type, _safe_float(return_pct), m)
        )
        # after recording, update weights lightly
        _update_weights_from_recent()
        return True
    except Exception:
        return False


def _update_weights_from_recent(lookback=80):
    """
    Simple online learning:
    - If recent outcomes are positive, slightly boost modules that were positive in signals,
      else reduce them.
    This is intentionally conservative to avoid overfitting.
    """
    if not DB_AVAILABLE:
        return

    try:
        sig = fetch_table("ai_signals")
        out = fetch_table("ai_outcomes")
        if sig is None or out is None or sig.empty or out.empty:
            return

        sig = sig.sort_values("ts", ascending=False).head(lookback)
        out = out.sort_values("ts", ascending=False).head(max(30, lookback // 2))

        # compute recent performance
        avg_ret = _safe_float(out["return_pct"].mean(), 0.0)

        # learning rate
        lr = 0.03
        direction = 1.0 if avg_ret >= 0 else -1.0

        w = _get_weights()

        # adjust based on which modules were "active" (signals dict)
        for _, r in sig.iterrows():
            try:
                payload = json.loads(r.get("payload_json") or "{}")
                modules = payload.get("modules", {}) or {}
                for m, info in modules.items():
                    m = str(m)
                    ms = _safe_float(info.get("score", 0))
                    if ms == 0:
                        continue
                    # if module score aligned with direction, boost a bit
                    if (ms > 0 and direction > 0) or (ms < 0 and direction < 0):
                        w[m] = min(w.get(m, 1.0) + lr, 1.8)
                    else:
                        w[m] = max(w.get(m, 1.0) - lr, 0.55)
            except Exception:
                continue

        # persist weights
        for m, ww in w.items():
            try:
                execute_query(
                    "UPDATE ai_weights SET weight=%s, updated_ts=CURRENT_TIMESTAMP WHERE module=%s",
                    (_safe_float(ww), str(m))
                )
            except Exception:
                pass

    except Exception:
        pass


# ============================================================
# 🧠 Master Brain (Upgraded)
# ============================================================

def generate_ai_report(symbol, timeframe="6mo"):
    """
    timeframe currently aligned with market_data.get_chart_history(period=...)
    """
    # init memory tables once (safe)
    _memory_init()

    try:
        df = get_chart_history(symbol, period=timeframe)
        df = _ensure_ohlcv(df)
        if df.empty:
            raise ValueError("No OHLCV")

        weights = _get_weights()

        # --- Modules ---
        s_candle, o_candle = _detect_advanced_patterns(df)
        s_struct, o_struct = _analyze_market_structure_basic(df)
        s_bos, o_bos, m_bos = _analyze_bos_ote(df)
        s_ichi, o_ichi, m_ichi = _analyze_ichimoku(df)
        s_sd, o_sd, m_sd = _analyze_supply_demand(df)
        s_vsa, o_vsa = _analyze_vsa_art_of_trading(df)
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)

        # weighted tech score
        tech_parts = {
            "candles": {"score": s_candle, "reasons": o_candle},
            "structure": {"score": s_struct, "reasons": o_struct},
            "bos_ote": {"score": s_bos, "reasons": o_bos},
            "ichimoku": {"score": s_ichi, "reasons": o_ichi},
            "supply_demand": {"score": s_sd, "reasons": o_sd},
            "vsa": {"score": s_vsa, "reasons": o_vsa},
        }
        fund_parts = {"fundamentals": {"score": s_fund, "reasons": o_fund}}

        tech_score = 0.0
        for k, v in tech_parts.items():
            tech_score += _safe_float(v["score"]) * _safe_float(weights.get(k, 1.0), 1.0)

        fund_score = _safe_float(s_fund) * _safe_float(weights.get("fundamentals", 1.0), 1.0)
        total_score = tech_score + fund_score

        # agreement bonus (if multiple modules align)
        module_scores = [s_candle, s_struct, s_bos, s_ichi, s_sd, s_vsa]
        pos_count = sum(1 for x in module_scores if _safe_float(x) > 0)
        neg_count = sum(1 for x in module_scores if _safe_float(x) < 0)
        agreement_bonus = 0
        if pos_count >= 4:
            agreement_bonus = 6
        elif neg_count >= 4:
            agreement_bonus = 6

        # --- Decision ---
        rec = "⚖️ محايد / مراقبة"
        clr = "#6c757d"
        strat = "السعر في منطقة حيرة. انتظر إشارة أوضح."
        strategy_tag = "Watch"

        # trend proxy: combine BOS + Ichimoku + Structure
        trend_bias = 0
        trend_bias += 1 if m_ichi.get("trend") == "bull" else (-1 if m_ichi.get("trend") == "bear" else 0)
        trend_bias += 1 if m_bos.get("bos") == "bull" else (-1 if m_bos.get("bos") == "bear" else 0)
        trend_bias += 1 if s_struct > 0 else (-1 if s_struct < 0 else 0)

        if total_score >= 9:
            rec = "💎 فرصة ماسية (Strong Buy)"
            clr = "#198754"
            strat = "توافق قوي بين: هيكل/إيشيموكو/عرض-طلب + دعم مالي."
            strategy_tag = "Trend"
        elif total_score >= 5:
            rec = "✅ شراء / تجميع"
            clr = "#28a745"
            strat = "الإشارات الإيجابية تغلب — ركّز على الدخول مع إعادة الاختبار."
            strategy_tag = "Trend" if trend_bias >= 1 else "Sniper"
        elif total_score <= -6:
            rec = "⛔ خروج / وقف خسارة"
            clr = "#dc3545"
            strat = "سلبية واضحة (كسر هيكل/سحابة/منطقة) — تقليل المخاطر."
            strategy_tag = "Sniper"
        elif (tech_score > 4 and fund_score < 0):
            rec = "⚡ مضاربة بحذر"
            clr = "#ffc107"
            strat = "فني قوي لكن المالي ضعيف — مضاربة بإدارة صارمة."
            strategy_tag = "Sniper"
        elif (fund_score > 4 and tech_score < 0):
            rec = "📉 استثمار قيمة"
            clr = "#0d6efd"
            strat = "مالي قوي لكن السعر ضعيف — مناسب للتجميع المتدرج."
            strategy_tag = "Trend"

        # reasons
        tech_reasons = []
        for k in ["bos_ote", "ichimoku", "supply_demand", "structure", "candles", "vsa"]:
            tech_reasons += (tech_parts.get(k, {}).get("reasons") or [])

        fund_reasons = o_fund or []

        if not tech_reasons:
            tech_reasons = ["حركة السعر طبيعية"]
        if not fund_reasons:
            fund_reasons = ["المؤشرات المالية طبيعية"]

        confidence, confidence_label = _calc_confidence(tech_score, fund_score, df, agreement_bonus=agreement_bonus)
        explainability = _build_explainability(tech_reasons, fund_reasons, total_score, tech_score, fund_score)

        rep = {
            "recommendation": rec,
            "color": clr,
            "strategy": strat,
            "strategy_tag": strategy_tag,  # IMPORTANT: use this for backtester mapping
            "tech_score": float(round(tech_score, 2)),
            "fund_score": float(round(fund_score, 2)),
            "total_score": float(round(total_score, 2)),
            "tech_reasons": tech_reasons,
            "fund_reasons": fund_reasons,
            "trend": "صاعد" if trend_bias >= 1 else ("هابط" if trend_bias <= -1 else "متذبذب"),
            "confidence": confidence,
            "confidence_label": confidence_label,
            "explainability": explainability,
            "modules": {
                # store module scores for learning
                "candles": {"score": s_candle},
                "structure": {"score": s_struct},
                "bos_ote": {"score": s_bos},
                "ichimoku": {"score": s_ichi},
                "supply_demand": {"score": s_sd},
                "vsa": {"score": s_vsa},
                "fundamentals": {"score": s_fund},
            },
            "meta": {
                "ichimoku": m_ichi,
                "bos_ote": m_bos,
                "supply_demand": m_sd,
            }
        }

        # log signal to memory
        _log_signal(symbol, timeframe, rep)

        return rep

    except Exception as e:
        return {
            "recommendation": "غير متاح",
            "color": "#6c757d",
            "strategy": "نقص بيانات",
            "strategy_tag": "Watch",
            "tech_reasons": [],
            "fund_reasons": [],
            "trend": "-",
            "confidence": 0,
            "confidence_label": "منخفضة",
            "explainability": {"positives": [], "negatives": [], "notes": [f"AI Engine Error: {e}"]},
        }


# ============================================================
# 🛡️ Portfolio Intelligence (preserved)
# ============================================================

def calculate_portfolio_risk_score(trades_df, cash_percent):
    try:
        if trades_df is None or trades_df.empty:
            return 0

        open_trades = trades_df[trades_df["status"] == "Open"]
        if open_trades.empty:
            return 0

        total_market_val = _safe_float(open_trades["market_value"].sum())
        if total_market_val == 0:
            return 0

        max_asset_weight = (_safe_float(open_trades["market_value"].max()) / total_market_val) * 100
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

        weighted_beta = 0.0
        total_val = _safe_float(open_positions_df["market_value"].sum())
        if total_val == 0:
            return {"scenarios": [], "insight": "غير متاح"}

        for _, row in open_positions_df.iterrows():
            w = _safe_float(row.get("market_value")) / total_val
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
            impact_pct = _safe_float(s["market_chg"]) * weighted_beta
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
                if _safe_float(row.get("gain_pct", 0)) < -10:
                    suggestions.append(("danger", f"🛑 خسارة تجاوزت -10% في {row.get('symbol','-')}"))
    except Exception:
        pass

    return suggestions
