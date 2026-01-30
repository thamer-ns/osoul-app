# ai_engine.py
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from market_data import get_chart_history
from financial_analysis import get_advanced_fundamental_ratios

# ============================================================
# 🧠 DB Helpers
# ============================================================

def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None

def _try_fetch(table_name: str) -> pd.DataFrame:
    _, fetch_table = _safe_import_db()
    if not fetch_table:
        return pd.DataFrame()
    try:
        df = fetch_table(table_name)
        if isinstance(df, pd.DataFrame):
            return df
        return pd.DataFrame()
    except Exception:
        return pd.DataFrame()

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
            sector TEXT,
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

def _get_weight(key: str, default=1.0):
    _, fetch_table = _safe_import_db()
    if not fetch_table:
        return float(default)
    _ensure_ai_tables()
    try:
        df = _try_fetch("ai_weights")
        if df.empty or "key" not in df.columns:
            return float(default)
        row = df[df["key"] == key]
        if row.empty:
            return float(default)
        return float(row.iloc[0].get("weight", default))
    except Exception:
        return float(default)

def _set_weight(key: str, weight: float):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()
    try:
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

# ============================================================
# 🧾 Logging AI Signals
# ============================================================

def log_ai_signal(symbol, timeframe, features: dict, report: dict, horizon_days=20, sector=None):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()
    try:
        execute_query(
            "INSERT INTO ai_signals (symbol, sector, timeframe, horizon_days, features_json, report_json) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                str(symbol),
                str(sector) if sector is not None else None,
                str(timeframe),
                int(horizon_days),
                json.dumps(features, ensure_ascii=False),
                json.dumps(report, ensure_ascii=False),
            ),
        )
        return True
    except Exception:
        return False

def update_ai_outcome(signal_id: int, outcome_return_pct: float):
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

# ============================================================
# ✅ 100% Mapping: ai_decisions <-> lab_equity
# ============================================================

def _normalize_ai_decisions_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    يجعل الكود مرن حتى لو أسماء الأعمدة تختلف شوي.
    بناءً على عيّنتك: ai_decisions فيها run_id + created_at + symbol + sector + strategy_key + timeframe + return_pct
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    # خريطة أسماء محتملة
    col_map = {
        "run_id": ["run_id", "id", "uuid"],
        "created_at": ["created_at", "created", "ts", "timestamp"],
        "symbol": ["symbol", "ticker"],
        "sector": ["sector", "industry"],
        "strategy_key": ["strategy_key", "strategy", "strategy_code"],
        "timeframe": ["timeframe", "tf"],
        "return_pct": ["return_pct", "ret", "return", "pnl_pct"],
        "final_value": ["final_value", "end_value", "portfolio_final", "equity_final"],
        "trades_count": ["trades_count", "n_trades", "trades"],
        "params_json": ["params_json", "params", "config_json"],
        "features_json": ["features_json", "features_snapshot", "features"],
        "report_json": ["report_json", "ai_report", "report"],
    }

    def pick(name):
        for c in col_map[name]:
            if c in out.columns:
                return c
        return None

    # rename to canonical if found
    ren = {}
    for k in ["run_id", "created_at", "symbol", "sector", "strategy_key", "timeframe",
              "return_pct", "final_value", "trades_count", "params_json", "features_json", "report_json"]:
        c = pick(k)
        if c and c != k:
            ren[c] = k

    if ren:
        out = out.rename(columns=ren)

    # types
    if "created_at" in out.columns:
        try:
            out["created_at"] = pd.to_datetime(out["created_at"])
        except Exception:
            pass

    for c in ["return_pct", "final_value"]:
        if c in out.columns:
            out[c] = pd.to_numeric(out[c], errors="coerce")

    return out

def _normalize_lab_equity_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    من عيّنتك: lab_equity فيها:
    trade_id / equity_id ، run_id ، date ، price? ، equity_value
    سنوحّدها: run_id, date, equity
    """
    if df is None or df.empty:
        return pd.DataFrame()

    out = df.copy()

    # احتماليات أسماء الأعمدة
    candidates_run = [c for c in ["run_id", "lab_run_id", "id"] if c in out.columns]
    candidates_date = [c for c in ["date", "dt", "time", "timestamp"] if c in out.columns]

    run_col = candidates_run[0] if candidates_run else None
    date_col = candidates_date[0] if candidates_date else None

    # equity col: نختار آخر عمود رقمي غالباً (مثل 100000)
    eq_col = None
    numeric_cols = [c for c in out.columns if c not in (run_col, date_col) and pd.api.types.is_numeric_dtype(out[c])]
    if numeric_cols:
        # غالباً equity هو آخر عمود رقمي
        eq_col = numeric_cols[-1]

    ren = {}
    if run_col and run_col != "run_id":
        ren[run_col] = "run_id"
    if date_col and date_col != "date":
        ren[date_col] = "date"
    if eq_col and eq_col != "equity":
        ren[eq_col] = "equity"

    if ren:
        out = out.rename(columns=ren)

    if "date" in out.columns:
        try:
            out["date"] = pd.to_datetime(out["date"])
        except Exception:
            pass

    if "equity" in out.columns:
        out["equity"] = pd.to_numeric(out["equity"], errors="coerce")

    return out

def get_learned_bias(symbol: str, sector: str = None, lookback: int = 100):
    """
    ✅ 100% من ai_decisions:
    - أفضل استراتيجية تاريخياً للسهم/القطاع
    - win_rate + avg_return
    - أشهر أسباب الفشل (إذا توفرت features_json/features_snapshot)
    """
    # 1) حاول من ai_decisions (مصدر الحقيقة عندك)
    dec = _try_fetch("ai_decisions")
    dec = _normalize_ai_decisions_df(dec)

    if not dec.empty and "symbol" in dec.columns:
        d = dec.copy()
        d["symbol"] = d["symbol"].astype(str)

        # فلترة
        d = d[d["symbol"] == str(symbol)]
        if sector and "sector" in d.columns:
            d = d[(d["sector"].astype(str) == str(sector)) | (d["sector"].isna())]

        # أحدث N
        if "created_at" in d.columns:
            d = d.sort_values("created_at", ascending=False).head(int(lookback))
        else:
            d = d.head(int(lookback))

        # لو لا يوجد return_pct
        if d.empty or "return_pct" not in d.columns or "strategy_key" not in d.columns:
            return {
                "ok": False,
                "source": "ai_decisions",
                "best_strategy": None,
                "win_rate": None,
                "avg_return": None,
                "n": 0,
                "top_fail_reasons": [],
            }

        d["win"] = (pd.to_numeric(d["return_pct"], errors="coerce").fillna(0) > 0).astype(int)

        grp = d.groupby("strategy_key", dropna=False).agg(
            n=("win", "count"),
            win_rate=("win", "mean"),
            avg_return=("return_pct", "mean"),
        ).reset_index()

        # تجاهل استراتيجيات قليلة التجارب جداً
        grp = grp.sort_values(["win_rate", "avg_return", "n"], ascending=[False, False, False])
        best = grp.iloc[0].to_dict() if not grp.empty else {}

        # أسباب فشل (اختياري)
        fail_reasons = []
        feat_col = None
        for c in ["features_json", "features_snapshot"]:
            if c in d.columns:
                feat_col = c
                break

        if feat_col:
            try:
                losers = d[d["win"] == 0].tail(200)
                counts = {}
                for _, r in losers.iterrows():
                    raw = r.get(feat_col)
                    if not raw:
                        continue
                    try:
                        feats = json.loads(raw) if isinstance(raw, str) else (raw or {})
                    except Exception:
                        feats = {}
                    # نعد إشارات 1
                    for k, v in (feats or {}).items():
                        if isinstance(v, (bool, int)) and int(v) == 1:
                            counts[k] = counts.get(k, 0) + 1
                fail_reasons = sorted(counts.items(), key=lambda x: x[1], reverse=True)[:8]
            except Exception:
                fail_reasons = []

        return {
            "ok": True,
            "source": "ai_decisions",
            "best_strategy": best.get("strategy_key"),
            "win_rate": float(best.get("win_rate", 0)) if best else 0.0,
            "avg_return": float(best.get("avg_return", 0)) if best else 0.0,
            "n": int(best.get("n", 0)) if best else 0,
            "top_fail_reasons": fail_reasons,
            "strategies_table": grp,  # مفيد للعرض إن احتجته
        }

    # 2) fallback: ai_signals (لو ما عندك ai_decisions)
    sig = _try_fetch("ai_signals")
    if sig.empty:
        return {"ok": False, "source": "none", "best_strategy": None, "win_rate": None, "avg_return": None, "n": 0, "top_fail_reasons": []}

    sig = sig.copy()
    if "symbol" in sig.columns:
        sig = sig[sig["symbol"].astype(str) == str(symbol)]
    if sector and "sector" in sig.columns:
        sig = sig[sig["sector"].astype(str) == str(sector)]

    sig = sig.dropna(subset=["outcome_win"])
    if sig.empty:
        return {"ok": False, "source": "ai_signals", "best_strategy": None, "win_rate": None, "avg_return": None, "n": 0, "top_fail_reasons": []}

    sig = sig.sort_values("created_at", ascending=False).head(int(lookback))

    # من ai_signals ما عندنا strategy_key عادة، فنرجع Bias عام
    win_rate = float(sig["outcome_win"].mean())
    avg_return = float(pd.to_numeric(sig["outcome_return_pct"], errors="coerce").fillna(0).mean())

    return {
        "ok": True,
        "source": "ai_signals",
        "best_strategy": None,
        "win_rate": win_rate,
        "avg_return": avg_return,
        "n": int(len(sig)),
        "top_fail_reasons": [],
    }

def learn_from_history(max_rows=400):
    """
    تعلّم أوزان features بشكل لطيف:
    - إذا عندك ai_decisions مع features_json => الأفضل
    - وإلا fallback على ai_signals
    """
    _ensure_ai_tables()

    # أولوية: ai_decisions
    dec = _try_fetch("ai_decisions")
    dec = _normalize_ai_decisions_df(dec)
    feat_col = None
    for c in ["features_json", "features_snapshot"]:
        if c in dec.columns:
            feat_col = c
            break

    if not dec.empty and "return_pct" in dec.columns and feat_col:
        d = dec.copy()
        if "created_at" in d.columns:
            d = d.sort_values("created_at", ascending=False).head(int(max_rows))
        else:
            d = d.head(int(max_rows))

        d["win"] = (pd.to_numeric(d["return_pct"], errors="coerce").fillna(0) > 0).astype(int)

        stats = {}
        for _, r in d.iterrows():
            win = int(r.get("win") or 0)
            raw = r.get(feat_col)
            if not raw:
                continue
            try:
                feats = json.loads(raw) if isinstance(raw, str) else (raw or {})
            except Exception:
                feats = {}
            for k, v in (feats or {}).items():
                if isinstance(v, (bool, int)) and int(v) in (0, 1):
                    stats.setdefault(k, {"wins": 0, "n": 0})
                    stats[k]["wins"] += win
                    stats[k]["n"] += 1

        updated = 0
        for k, s in stats.items():
            if s["n"] < 20:
                continue
            win_rate = s["wins"] / s["n"]
            w = _get_weight(k, 1.0)
            if win_rate >= 0.58:
                w = min(w + 0.05, 2.0)
            elif win_rate <= 0.42:
                w = max(w - 0.05, 0.3)
            if _set_weight(k, w):
                updated += 1

        return {"ok": True, "source": "ai_decisions", "updated": updated, "features": len(stats)}

    # fallback: ai_signals
    sig = _try_fetch("ai_signals")
    if sig.empty:
        return {"ok": False, "reason": "No history tables available"}

    sig = sig.dropna(subset=["outcome_win"])
    if sig.empty:
        return {"ok": True, "source": "ai_signals", "updated": 0, "features": 0}

    sig = sig.sort_values("created_at", ascending=False).head(int(max_rows))

    stats = {}
    for _, r in sig.iterrows():
        try:
            feats = json.loads(r.get("features_json") or "{}")
            win = int(r.get("outcome_win") or 0)
            for k, v in feats.items():
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
        if win_rate >= 0.58:
            w = min(w + 0.05, 2.0)
        elif win_rate <= 0.42:
            w = max(w - 0.05, 0.3)
        if _set_weight(k, w):
            updated += 1

    return {"ok": True, "source": "ai_signals", "updated": updated, "features": len(stats)}

# ============================================================
# 🕯️ 1) Advanced Candlestick Patterns
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

    if is_c1_red and body2 < body1 * 0.4 and is_c3_green:
        midpoint = c1["Open"] - (body1 / 2)
        if c3["Close"] > midpoint:
            score += 3
            patterns.append("✨ نجمة الصباح - انعكاس إيجابي قوي")

    if is_c1_green and body2 < body1 * 0.4 and is_c3_red:
        midpoint = c1["Open"] + (body1 / 2)
        if c3["Close"] < midpoint:
            score -= 3
            patterns.append("🌑 نجمة المساء - خروج/انعكاس سلبي")

    if is_c2_red and is_c3_green and c3["Open"] > c2["Close"] and c3["Close"] < c2["Open"]:
        score += 2
        patterns.append("🤰 الحرامي الشرائي - ضعف الزخم الهابط")

    if is_c2_red and is_c3_green and c3["Open"] < c2["Close"] and c3["Close"] > c2["Open"]:
        score += 2
        patterns.append("🔥 ابتلاع شرائي - سيطرة مشترين")

    return score, patterns

# ============================================================
# 📈 2) Market Structure + pivots
# ============================================================

def _pivot_points(series, left=3, right=3, mode="high"):
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

    ph = _pivot_points(high, 3, 3, "high")
    pl = _pivot_points(low, 3, 3, "low")

    last_swing_high = ph[-1][1] if ph else float(high.iloc[-25:-2].max())
    last_swing_low = pl[-1][1] if pl else float(low.iloc[-25:-2].min())

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

    try:
        if len(ph) >= 1 and len(pl) >= 1:
            last_high_i, last_high = ph[-1]
            last_low_i, last_low = pl[-1]
            if last_low_i < last_high_i:
                fib50 = last_low + 0.5 * (last_high - last_low)
                if abs(curr - fib50) / max(curr, 1e-9) < 0.01:
                    score += 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة دخول أفضل)")
            else:
                fib50 = last_high - 0.5 * (last_high - last_low)
                if abs(curr - fib50) / max(curr, 1e-9) < 0.01:
                    score -= 1
                    obs.append("🎯 OTE: السعر قريب 50% فيبو (منطقة بيع أفضل)")
    except Exception:
        pass

    return score, obs

# ============================================================
# 🧩 3) SMC: Liquidity Sweep + Order Block
# ============================================================

def _detect_liquidity_sweep(df, lookback=30):
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

    if h > prev_high and c < prev_high:
        score -= 2
        feats["liq_sweep_high"] = 1
        obs.append("🧲 صيد سيولة شرائية (اختراق زائف للأعلى)")

    if l < prev_low and c > prev_low:
        score += 2
        feats["liq_sweep_low"] = 1
        obs.append("🧲 صيد سيولة بيعية (اختراق زائف للأسفل)")

    return score, obs, feats

def _detect_order_block(df):
    if df is None or len(df) < 80:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"bull_ob_retest": 0, "bear_ob_retest": 0}

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)

    rng = (high - low)
    avg_rng = float(rng.iloc[-40:].mean()) if len(rng) >= 40 else float(rng.mean())

    window = df.iloc[-25:]
    idx_impulse_up = None
    for i in range(len(window) - 1, 1, -1):
        r = float(window["High"].iloc[i] - window["Low"].iloc[i])
        if r > avg_rng * 1.4 and float(window["Close"].iloc[i]) > float(window["Open"].iloc[i]):
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
            if (last_l <= ob_high) and (last_c >= ob_low):
                score += 2
                feats["bull_ob_retest"] = 1
                obs.append("🧱 Bullish Order Block retest (منطقة شراء محتملة)")

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
# ☁️ 4) Ichimoku
# ============================================================

def _ichimoku(df):
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
    feats = {"ichi_bull": 0, "ichi_bear": 0, "ichi_tk_cross_up": 0, "ichi_tk_cross_dn": 0}

    tenkan, kijun, span_a, span_b, chikou = _ichimoku(df)
    close = df["Close"].astype(float)

    c = float(close.iloc[-1])
    sa = float(span_a.iloc[-1]) if not pd.isna(span_a.iloc[-1]) else np.nan
    sb = float(span_b.iloc[-1]) if not pd.isna(span_b.iloc[-1]) else np.nan
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

    if float(tenkan.iloc[-1]) > float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) <= float(kijun.iloc[-2]):
        score += 1
        feats["ichi_tk_cross_up"] = 1
        obs.append("🔀 تقاطع تنكن فوق كيجن (إشارة دعم للشراء)")

    if float(tenkan.iloc[-1]) < float(kijun.iloc[-1]) and float(tenkan.iloc[-2]) >= float(kijun.iloc[-2]):
        score -= 1
        feats["ichi_tk_cross_dn"] = 1
        obs.append("🔀 تقاطع تنكن تحت كيجن (إشارة دعم للبيع)")

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
# 💰 5) Fundamentals
# ============================================================

def _analyze_financial_golden_rules(symbol):
    try:
        metrics = get_advanced_fundamental_ratios(symbol)
    except Exception:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"fund_strong_piotroski": 0, "fund_weak_piotroski": 0, "fund_graham_fair": 0, "fund_neg_ocf": 0}

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
# 📊 6) VSA
# ============================================================

def _analyze_vsa_art_of_trading(df):
    if df is None or len(df) < 50:
        return 0, [], {}

    score = 0
    obs = []
    feats = {"vsa_upthrust": 0, "vsa_stopping_volume": 0, "vsa_distribution": 0}

    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    open_ = df["Open"].astype(float)
    vol = df["Volume"].astype(float)

    curr = df.iloc[-1]
    avg_vol = float(vol.iloc[-20:].mean())
    rng = (high - low)
    avg_rng = float(rng.iloc[-20:].mean())

    r = float(curr["High"] - curr["Low"])

    if (float(curr["Close"]) > float(curr["Open"])) and (float(curr["Volume"]) > avg_vol * 1.5) and (r > avg_rng * 1.2):
        if float(curr["Close"]) <= float(curr["Low"]) + 0.25 * r:
            score -= 2
            feats["vsa_upthrust"] = 1
            obs.append("VSA: Upthrust (ضعف/تصريف محتمل)")

    if (float(curr["Close"]) < float(curr["Open"])) and (float(curr["Volume"]) > avg_vol * 1.5) and (r > avg_rng * 1.1):
        if float(curr["Close"]) >= float(curr["Low"]) + 0.5 * r:
            score += 2
            feats["vsa_stopping_volume"] = 1
            obs.append("VSA: Stopping Volume (امتصاص بيع/قوة)")

    if float(curr["Volume"]) > avg_vol * 1.7:
        if float(curr["Close"]) < float(curr["Low"]) + 0.55 * r and float(curr["Close"]) > float(curr["Open"]):
            score -= 1
            feats["vsa_distribution"] = 1
            obs.append("VSA: تفريغ محتمل (حجم عالي وإغلاق ليس على القمة)")

    return score, obs, feats

# ============================================================
# 🧱 7) Support/Resistance Zones
# ============================================================

def _support_resistance_zones(df, lookback=120, max_levels=6):
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
# ✅ Confidence + Explainability
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
# 🧠 Master Brain (مع Calibration من ai_decisions)
# ============================================================

def generate_ai_report(symbol, timeframe="1D", sector=None):
    try:
        df = get_chart_history(symbol, period="6mo")
        if df is None or df.empty:
            raise ValueError("no data")

        for col in ["Open", "High", "Low", "Close", "Volume"]:
            if col not in df.columns:
                raise ValueError(f"missing {col}")

        s_candle, o_candle = _detect_advanced_patterns(df)
        s_struct, o_struct = _analyze_market_structure(df)
        s_liq, o_liq, f_liq = _detect_liquidity_sweep(df)
        s_ob, o_ob, f_ob = _detect_order_block(df)
        s_ichi, o_ichi, f_ichi = _analyze_ichimoku(df)
        s_vsa, o_vsa, f_vsa = _analyze_vsa_art_of_trading(df)
        s_sr, o_sr, f_sr = _analyze_sr(df)
        s_fund, o_fund, m_fund = _analyze_financial_golden_rules(symbol)

        base_tech = s_candle + s_struct + s_vsa + s_ichi + s_ob + s_liq + s_sr
        tech_reasons = (o_struct or []) + (o_candle or []) + (o_vsa or []) + (o_ichi or []) + (o_ob or []) + (o_liq or []) + (o_sr or [])

        features = {}
        fund_feats = (m_fund or {}).get("_fund_features", {})
        for d in [f_liq, f_ob, f_ichi, f_vsa, f_sr, fund_feats]:
            try:
                for k, v in (d or {}).items():
                    if isinstance(v, (bool, int)):
                        features[k] = int(v)
            except Exception:
                pass

        weighted_bonus = 0.0
        for k, v in features.items():
            if int(v) == 1:
                weighted_bonus += (0.2 * (_get_weight(k, 1.0) - 1.0))

        tech_score = float(base_tech + weighted_bonus)
        fund_score = float(s_fund)
        total_score = float(tech_score + fund_score)

        # ✅ Calibration من نتائج المختبر (ai_decisions) — يرفع/يخفض الثقة أو يلمّح لأفضل استراتيجية تاريخياً
        bias = get_learned_bias(symbol, sector=sector, lookback=100)
        # تأثير خفيف على التقييم فقط (بدون تغيير منطق التوصية)
        calib_note = None
        if bias.get("ok") and bias.get("n", 0) >= 8:
            wr = float(bias.get("win_rate", 0))
            ar = float(bias.get("avg_return", 0))
            best_strat = bias.get("best_strategy")

            # تعديل لطيف: win_rate العالي يدعم القرار، المنخفض ينقصه
            if wr >= 0.60:
                tech_score += 0.6
                total_score += 0.6
                calib_note = f"📌 Calibration: أفضل تاريخياً ({best_strat}) | WinRate={wr:.0%} | AvgRet={ar:.2f}%"
            elif wr <= 0.45:
                tech_score -= 0.6
                total_score -= 0.6
                calib_note = f"📌 Calibration: أداء ضعيف تاريخياً | WinRate={wr:.0%} | AvgRet={ar:.2f}%"

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

        if calib_note:
            explainability["notes"] = [calib_note] + (explainability.get("notes") or [])

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
            "learned_bias": {
                "source": bias.get("source"),
                "best_strategy": bias.get("best_strategy"),
                "win_rate": bias.get("win_rate"),
                "avg_return": bias.get("avg_return"),
                "n": bias.get("n"),
                "top_fail_reasons": bias.get("top_fail_reasons", []),
            },
        }

        log_ai_signal(symbol, timeframe, features, report, horizon_days=20, sector=sector)
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
            "learned_bias": {"source": "none", "best_strategy": None, "win_rate": None, "avg_return": None, "n": 0, "top_fail_reasons": []},
        }

# ============================================================
# 🛡️ Portfolio Intelligence
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
