# ai_engine.py
import json
import re
import uuid
import traceback
import pandas as pd
import numpy as np
from datetime import datetime

AI_ENGINE_VERSION = "2.1.0"

# ============================================================
# Helpers
# ============================================================
def _normalize_symbol(sym: str) -> str:
    sym = (sym or "").strip().upper()
    if sym.isdigit():
        return f"{sym}.SR"
    sym = sym.replace(" ", "").replace("-", "")
    if sym.endswith("SR") and ".SR" not in sym:
        sym = sym.replace("SR", ".SR")
    return sym


def _now_str():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _safe_import_db():
    try:
        from database import execute_query, fetch_table
        return execute_query, fetch_table
    except Exception:
        return None, None


def _try_exec(sql: str, params=()):
    """
    Portable execute:
    - Postgres style placeholders: %s
    - SQLite style placeholders: ?
    نحاول أولاً كما هو، وإذا فشل نجرب استبدال %s بـ ?
    """
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    try:
        execute_query(sql, params)
        return True
    except Exception:
        try:
            sql2 = sql.replace("%s", "?")
            execute_query(sql2, params)
            return True
        except Exception:
            return False


def _safe_fetch_table(name: str):
    _, fetch_table = _safe_import_db()
    if not fetch_table:
        return None
    try:
        df = fetch_table(name)
        if isinstance(df, pd.DataFrame):
            return df
        return None
    except Exception:
        return None


def _ensure_ohlcv_columns(df: pd.DataFrame) -> pd.DataFrame:
    """
    يطبع أسماء الأعمدة إلى Open/High/Low/Close/Volume
    ويفك MultiIndex إذا موجود.
    """
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return df

    try:
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [str(c[-1]) for c in df.columns]
    except Exception:
        pass

    cols = {c: c for c in df.columns}
    lower = {str(c).lower(): c for c in df.columns}

    def pick(*names):
        for n in names:
            if n in cols:
                return cols[n]
            if n.lower() in lower:
                return lower[n.lower()]
        return None

    m_open = pick("Open", "open", "OPEN")
    m_high = pick("High", "high", "HIGH")
    m_low = pick("Low", "low", "LOW")
    m_close = pick("Close", "close", "Adj Close", "adjclose", "adj_close", "ADJ CLOSE")
    m_vol = pick("Volume", "volume", "VOL", "vol")

    ren = {}
    if m_open and m_open != "Open":
        ren[m_open] = "Open"
    if m_high and m_high != "High":
        ren[m_high] = "High"
    if m_low and m_low != "Low":
        ren[m_low] = "Low"
    if m_close and m_close != "Close":
        ren[m_close] = "Close"
    if m_vol and m_vol != "Volume":
        ren[m_vol] = "Volume"

    if ren:
        df = df.rename(columns=ren)

    needed = ["Open", "High", "Low", "Close"]
    for c in needed:
        if c not in df.columns:
            raise ValueError(f"missing {c}")

    if "Volume" not in df.columns:
        df["Volume"] = 0.0

    for c in ["Open", "High", "Low", "Close", "Volume"]:
        try:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        except Exception:
            pass

    df = df.dropna(subset=["Open", "High", "Low", "Close"]).copy()
    return df


# ============================================================
# ✅ Cross-DB table schemas (SQLite/Postgres)
# ============================================================
def _ensure_ai_tables():
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False

    ok1 = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_signals (
        id TEXT PRIMARY KEY,
        created_at TEXT,
        symbol TEXT,
        sector TEXT,
        timeframe TEXT,
        horizon_days INTEGER DEFAULT 20,
        strategy_name TEXT,
        features_json TEXT,
        exit_features_json TEXT,
        report_json TEXT,
        outcome_return_pct REAL,
        outcome_win INTEGER
    )
    """, ())

    ok2 = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_weights (
        key TEXT PRIMARY KEY,
        weight REAL DEFAULT 1.0,
        updated_at TEXT
    )
    """, ())

    ok3 = _try_exec("""
    CREATE TABLE IF NOT EXISTS ai_user_rules (
        id TEXT PRIMARY KEY,
        created_at TEXT,
        title TEXT,
        rule_text TEXT,
        parsed_json TEXT,
        enabled INTEGER DEFAULT 1
    )
    """, ())

    return bool(ok1 and ok2 and ok3)


# ============================================================
# Logging
# ============================================================
def log_ai_signal(symbol, timeframe, features: dict, report: dict, horizon_days=20, sector=None, strategy_name=None):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return None

    _ensure_ai_tables()
    signal_id = str(uuid.uuid4())
    try:
        _try_exec(
            """
            INSERT INTO ai_signals
            (id, created_at, symbol, sector, timeframe, horizon_days, strategy_name, features_json, report_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                signal_id,
                _now_str(),
                str(symbol),
                (str(sector) if sector is not None else None),
                str(timeframe),
                int(horizon_days),
                (str(strategy_name) if strategy_name is not None else None),
                json.dumps(features or {}, ensure_ascii=False),
                json.dumps(report or {}, ensure_ascii=False),
            ),
        )
        return signal_id
    except Exception:
        return None


def update_ai_outcome(signal_id: str, outcome_return_pct: float, exit_features: dict = None):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()
    try:
        win = 1 if float(outcome_return_pct) > 0 else 0
        if exit_features is not None:
            _try_exec(
                "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s, exit_features_json=%s WHERE id=%s",
                (float(outcome_return_pct), int(win), json.dumps(exit_features, ensure_ascii=False), str(signal_id)),
            )
        else:
            _try_exec(
                "UPDATE ai_signals SET outcome_return_pct=%s, outcome_win=%s WHERE id=%s",
                (float(outcome_return_pct), int(win), str(signal_id)),
            )
        return True
    except Exception:
        return False


# ============================================================
# Weights (Simple Online Learning)
# ============================================================
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
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()

    ok = _try_exec(
        """
        INSERT INTO ai_weights (key, weight, updated_at)
        VALUES (%s,%s,%s)
        ON CONFLICT(key) DO UPDATE
        SET weight=EXCLUDED.weight, updated_at=EXCLUDED.updated_at
        """,
        (str(key), float(weight), _now_str()),
    )
    if ok:
        return True

    try:
        _try_exec("DELETE FROM ai_weights WHERE key=%s", (str(key),))
        _try_exec(
            "INSERT INTO ai_weights (key, weight, updated_at) VALUES (%s,%s,%s)",
            (str(key), float(weight), _now_str())
        )
        return True
    except Exception:
        return False


def learn_from_history(max_rows=400):
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()
    try:
        df = fetch_table("ai_signals")
        if df is None or df.empty:
            return {"ok": True, "updated": 0}

        if "outcome_win" not in df.columns:
            return {"ok": True, "updated": 0}

        df = df.dropna(subset=["outcome_win"])
        if df.empty:
            return {"ok": True, "updated": 0}

        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False)

        df = df.head(int(max_rows))

        stats = {}
        for _, r in df.iterrows():
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

        return {"ok": True, "updated": updated, "features": len(stats)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ============================================================
# 🧠 User Rules
# ============================================================
def _parse_user_rule(text: str):
    t = (text or "").strip().lower()

    parsed = {
        "raw": text,
        "conditions": [],
        "direction": None,
        "boost": 1.5,
        "tags": [],
    }

    if any(k in t for k in ["شراء", "تجميع", "صعود", "buy"]):
        parsed["direction"] = "buy"
    if any(k in t for k in ["بيع", "خروج", "هبوط", "sell"]):
        parsed["direction"] = "sell"

    if "ماكد" in t or "macd" in t:
        if any(k in t for k in ["تقاطع", "cross"]) and any(k in t for k in ["صعود", "ايجابي", "up"]):
            parsed["conditions"].append({"type": "macd_cross", "value": "up"})
            parsed["tags"].append("MACD_CROSS_UP")
        if any(k in t for k in ["تقاطع", "cross"]) and any(k in t for k in ["هبوط", "سلبي", "down"]):
            parsed["conditions"].append({"type": "macd_cross", "value": "down"})
            parsed["tags"].append("MACD_CROSS_DN")

        if any(k in t for k in ["خط الصفر", "zero"]):
            if any(k in t for k in ["فوق", "اختراق", "up", "اعلى"]):
                parsed["conditions"].append({"type": "macd_zero", "value": "above"})
                parsed["tags"].append("MACD_ABOVE_ZERO")
            if any(k in t for k in ["تحت", "down", "اسفل"]):
                parsed["conditions"].append({"type": "macd_zero", "value": "below"})
                parsed["tags"].append("MACD_BELOW_ZERO")

    if "rsi" in t or "مؤشر القوة النسبية" in t or "القوة النسبية" in t:
        m = re.search(r"(?:rsi|القوة)\s*(?:فوق|اعلى|>)\s*(\d+)", t)
        if m:
            parsed["conditions"].append({"type": "rsi_gt", "value": float(m.group(1))})
            parsed["tags"].append("RSI_GT")
        m = re.search(r"(?:rsi|القوة)\s*(?:تحت|اقل|<)\s*(\d+)", t)
        if m:
            parsed["conditions"].append({"type": "rsi_lt", "value": float(m.group(1))})
            parsed["tags"].append("RSI_LT")
        if "فوق 70" in t:
            parsed["conditions"].append({"type": "rsi_gt", "value": 70.0})
            parsed["tags"].append("RSI_GT_70")
        if "تحت 30" in t:
            parsed["conditions"].append({"type": "rsi_lt", "value": 30.0})
            parsed["tags"].append("RSI_LT_30")

    if "sma" in t or "متوسط" in t or "موفينج" in t:
        m = re.search(r"(?:sma|متوسط)\s*(\d+)", t)
        if m:
            n = int(m.group(1))
            if any(k in t for k in ["اختراق", "فوق", "اعلى"]):
                parsed["conditions"].append({"type": "close_above_sma", "value": n})
                parsed["tags"].append(f"CLOSE_ABOVE_SMA{n}")
            if any(k in t for k in ["كسر", "تحت", "اسفل"]):
                parsed["conditions"].append({"type": "close_below_sma", "value": n})
                parsed["tags"].append(f"CLOSE_BELOW_SMA{n}")

    m = re.search(r"(?:boost|قوة|تأثير)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
    if m:
        parsed["boost"] = float(m.group(1))

    return parsed


def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()
    rule_text = (rule_text or "").strip()
    if not rule_text:
        return {"ok": False, "reason": "empty"}

    parsed = _parse_user_rule(rule_text)
    try:
        _try_exec(
            "INSERT INTO ai_user_rules (id, created_at, title, rule_text, parsed_json, enabled) VALUES (%s,%s,%s,%s,%s,%s)",
            (
                str(uuid.uuid4()),
                _now_str(),
                (title or "قاعدة مستخدم"),
                rule_text,
                json.dumps(parsed, ensure_ascii=False),
                int(enabled),
            ),
        )
        return {"ok": True, "parsed": parsed}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def load_user_rules(enabled_only=True, max_rows=50):
    _ensure_ai_tables()
    df = _safe_fetch_table("ai_user_rules")
    if df is None or df.empty:
        return []
    try:
        if enabled_only and "enabled" in df.columns:
            df = df[df["enabled"].astype(int) == 1]
        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False)
        df = df.head(int(max_rows))
        rules = []
        for _, r in df.iterrows():
            pj = r.get("parsed_json")
            try:
                parsed = json.loads(pj) if pj else _parse_user_rule(str(r.get("rule_text") or ""))
            except Exception:
                parsed = _parse_user_rule(str(r.get("rule_text") or ""))
            rules.append({
                "id": r.get("id"),
                "title": r.get("title") or "قاعدة مستخدم",
                "rule_text": r.get("rule_text") or "",
                "parsed": parsed,
            })
        return rules
    except Exception:
        return []


def _eval_user_rule(parsed_rule: dict, df: pd.DataFrame, ind: dict):
    if not parsed_rule:
        return False, 0.0, "", {}

    conds = parsed_rule.get("conditions") or []
    if not conds:
        return False, 0.0, "", {}

    if df is None or df.empty or len(df) < 3:
        return False, 0.0, "", {}

    boost = float(parsed_rule.get("boost") or 1.5)
    direction = parsed_rule.get("direction")

    close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])

    rsi14 = float(ind.get("rsi14").iloc[-1]) if isinstance(ind.get("rsi14"), pd.Series) else None
    macd = float(ind.get("macd").iloc[-1]) if isinstance(ind.get("macd"), pd.Series) else None
    macd_prev = float(ind.get("macd").iloc[-2]) if isinstance(ind.get("macd"), pd.Series) else None
    sig = float(ind.get("macd_signal").iloc[-1]) if isinstance(ind.get("macd_signal"), pd.Series) else None
    sig_prev = float(ind.get("macd_signal").iloc[-2]) if isinstance(ind.get("macd_signal"), pd.Series) else None

    sma20 = float(ind.get("sma20").iloc[-1]) if isinstance(ind.get("sma20"), pd.Series) else None
    sma50 = float(ind.get("sma50").iloc[-1]) if isinstance(ind.get("sma50"), pd.Series) else None
    sma200 = float(ind.get("sma200").iloc[-1]) if isinstance(ind.get("sma200"), pd.Series) else None

    def _sma_by_n(n: int):
        if n == 20:
            return sma20
        if n == 50:
            return sma50
        if n == 200:
            return sma200
        return None

    def ok_one(c):
        t = c.get("type")
        v = c.get("value")

        if t == "macd_cross" and macd is not None and sig is not None and macd_prev is not None and sig_prev is not None:
            if v == "up":
                return (macd > sig) and (macd_prev <= sig_prev)
            if v == "down":
                return (macd < sig) and (macd_prev >= sig_prev)

        if t == "macd_zero" and macd is not None:
            if v == "above":
                return macd > 0
            if v == "below":
                return macd < 0

        if t == "rsi_gt" and rsi14 is not None:
            return rsi14 > float(v)
        if t == "rsi_lt" and rsi14 is not None:
            return rsi14 < float(v)

        if t == "close_above_sma":
            n = int(v)
            s = _sma_by_n(n)
            if s is None:
                return False
            return close > s and prev_close <= s

        if t == "close_below_sma":
            n = int(v)
            s = _sma_by_n(n)
            if s is None:
                return False
            return close < s and prev_close >= s

        return False

    hits = [ok_one(c) for c in conds]
    if not all(hits):
        return False, 0.0, "", {}

    delta = boost
    if direction == "sell":
        delta = -abs(boost)
    elif direction == "buy":
        delta = abs(boost)

    reason = f"📌 قاعدة مستخدم مطبقة: {parsed_rule.get('raw','')}"
    feats = {}
    for tag in (parsed_rule.get("tags") or []):
        feats[f"user_rule_{str(tag).lower()}"] = 1

    return True, float(delta), reason, feats


# ============================================================
# Indicators + Levels
# ============================================================
def _compute_indicators(df: pd.DataFrame):
    out = {}
    if df is None or df.empty or len(df) < 60:
        return out

    close = df["Close"].astype(float)
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    vol = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0] * len(df), index=df.index)

    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()
    out["sma200"] = close.rolling(200).mean()

    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    out["rsi14"] = rsi.bfill().fillna(50)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = hist

    # ATR(14)
    tr1 = (high - low).abs()
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr14 = tr.rolling(14).mean()
    out["atr14"] = atr14

    # Volume MA
    out["vol_ma20"] = vol.rolling(20).mean()

    # Fibonacci (آخر موجة 60 شمعة تقريباً)
    w = min(60, len(df))
    hh = high.tail(w).max()
    ll = low.tail(w).min()
    fib382 = ll + (hh - ll) * 0.382
    fib5 = ll + (hh - ll) * 0.5
    fib618 = ll + (hh - ll) * 0.618
    out["fib382"] = fib382
    out["fib50"] = fib5
    out["fib618"] = fib618
    out["swing_high"] = hh
    out["swing_low"] = ll

    return out


def _detect_support_resistance(df: pd.DataFrame):
    """
    دعم/مقاومة بسيط:
    - Pivot Low/High محلية
    - يرجع أقرب دعم وأقرب مقاومة
    """
    if df is None or df.empty or len(df) < 30:
        return None, None

    d = df.copy().tail(120)
    high = d["High"].astype(float)
    low = d["Low"].astype(float)
    close = d["Close"].astype(float)

    # pivots
    piv_lows = []
    piv_highs = []
    for i in range(2, len(d) - 2):
        if low.iloc[i] < low.iloc[i-1] and low.iloc[i] < low.iloc[i-2] and low.iloc[i] < low.iloc[i+1] and low.iloc[i] < low.iloc[i+2]:
            piv_lows.append(low.iloc[i])
        if high.iloc[i] > high.iloc[i-1] and high.iloc[i] > high.iloc[i-2] and high.iloc[i] > high.iloc[i+1] and high.iloc[i] > high.iloc[i+2]:
            piv_highs.append(high.iloc[i])

    if not piv_lows:
        piv_lows = [low.min()]
    if not piv_highs:
        piv_highs = [high.max()]

    px = float(close.iloc[-1])
    supports = sorted([x for x in piv_lows if x <= px], reverse=True)
    resists = sorted([x for x in piv_highs if x >= px])

    sup = supports[0] if supports else float(low.min())
    res = resists[0] if resists else float(high.max())
    return float(sup), float(res)


def _tf_horizon_days(timeframe: str):
    tf = (timeframe or "1d").lower().strip()
    if tf in ["1d", "d", "day"]:
        return 20
    if tf in ["1wk", "1w", "week"]:
        return 8 * 5
    if tf in ["1mo", "1m", "month"]:
        return 6 * 20
    return 20


# ============================================================
# Core: generate_ai_report (Unified Report Schema)
# ============================================================
def generate_ai_report(symbol: str, timeframe: str = "1d"):
    """
    ✅ يرجع تقرير موحّد للواجهة:
    {
      recommendation, score(0-100), confidence(0-100),
      summary_text (سبب التوصية كنص واحد مرتب),
      entry: {entry_zone, entry_note},
      risk: {stop, invalidation, rr},
      targets: [{name, price, rr}],
      scenarios: [{name, probability, plan, targets, stop}],
      evidence: {positives, negatives, signals, notes},
      risk_gates: [{gate, status, note}],
      levels: {support, resistance, fib382,...},
      meta: {symbol, timeframe, as_of, engine_version}
    }
    """
    try:
        sym = _normalize_symbol(symbol)
        tf = (timeframe or "1d").lower().strip()

        # -------- Fetch OHLCV --------
        from market_data import get_chart_history
        try:
            df = get_chart_history(sym, period="2y", interval=tf)  # إن كانت مدعومة
        except TypeError:
            df = get_chart_history(sym, "2y")  # fallback

        if df is None:
            return {"__error__": "no_data", "symbol": sym, "timeframe": tf}

        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        if df.empty:
            return {"__error__": "empty_data", "symbol": sym, "timeframe": tf}

        df = _ensure_ohlcv_columns(df)
        if len(df) < 80:
            # نجمع مؤشرات أقل
            df = df.copy()

        ind = _compute_indicators(df)
        close = float(df["Close"].iloc[-1])
        prev_close = float(df["Close"].iloc[-2])

        # -------- Levels --------
        support, resistance = _detect_support_resistance(df)
        swing_high = float(ind.get("swing_high", np.nan)) if ind else np.nan
        swing_low = float(ind.get("swing_low", np.nan)) if ind else np.nan
        fib382 = float(ind.get("fib382", np.nan)) if ind else np.nan
        fib50 = float(ind.get("fib50", np.nan)) if ind else np.nan
        fib618 = float(ind.get("fib618", np.nan)) if ind else np.nan

        # -------- Signals --------
        positives = []
        negatives = []
        notes = []
        signals = {}

        sma20 = float(ind["sma20"].iloc[-1]) if "sma20" in ind else np.nan
        sma50 = float(ind["sma50"].iloc[-1]) if "sma50" in ind else np.nan
        sma200 = float(ind["sma200"].iloc[-1]) if "sma200" in ind else np.nan

        rsi14 = float(ind["rsi14"].iloc[-1]) if "rsi14" in ind else 50.0
        macd = float(ind["macd"].iloc[-1]) if "macd" in ind else 0.0
        macd_prev = float(ind["macd"].iloc[-2]) if "macd" in ind and len(ind["macd"]) > 2 else macd
        sig = float(ind["macd_signal"].iloc[-1]) if "macd_signal" in ind else 0.0
        sig_prev = float(ind["macd_signal"].iloc[-2]) if "macd_signal" in ind and len(ind["macd_signal"]) > 2 else sig

        atr14 = float(ind["atr14"].iloc[-1]) if "atr14" in ind and not ind["atr14"].isna().iloc[-1] else max(close * 0.02, 0.01)
        vol_ma = float(ind["vol_ma20"].iloc[-1]) if "vol_ma20" in ind and not ind["vol_ma20"].isna().iloc[-1] else 0.0
        vol_now = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0

        # Trend regime
        trend_up = (close > sma50) and (sma50 > sma200) if np.isfinite(sma50) and np.isfinite(sma200) else False
        trend_dn = (close < sma50) and (sma50 < sma200) if np.isfinite(sma50) and np.isfinite(sma200) else False

        signals["trend_up"] = int(trend_up)
        signals["trend_dn"] = int(trend_dn)

        if trend_up:
            positives.append("الاتجاه العام صاعد (السعر فوق MA50 و MA50 فوق MA200).")
        elif trend_dn:
            negatives.append("الاتجاه العام هابط (السعر تحت MA50 و MA50 تحت MA200).")
        else:
            notes.append("الاتجاه العام متذبذب/انتقالي (غير محسوم).")

        # RSI
        signals["rsi_overbought"] = int(rsi14 >= 70)
        signals["rsi_oversold"] = int(rsi14 <= 30)

        if rsi14 >= 70:
            negatives.append(f"RSI مرتفع ({rsi14:.1f}) → احتمال تهدئة/تصحيح.")
        elif rsi14 <= 30:
            positives.append(f"RSI منخفض ({rsi14:.1f}) → احتمال ارتداد.")
        else:
            notes.append(f"RSI طبيعي ({rsi14:.1f}).")

        # MACD cross
        macd_cross_up = (macd > sig) and (macd_prev <= sig_prev)
        macd_cross_dn = (macd < sig) and (macd_prev >= sig_prev)
        signals["macd_cross_up"] = int(macd_cross_up)
        signals["macd_cross_dn"] = int(macd_cross_dn)

        if macd_cross_up:
            positives.append("تقاطع MACD صعودًا (تحسن زخم).")
        if macd_cross_dn:
            negatives.append("تقاطع MACD هبوطًا (ضعف زخم).")

        # Volume confirmation
        vol_spike = (vol_ma > 0) and (vol_now > 1.5 * vol_ma)
        signals["volume_spike"] = int(vol_spike)
        if vol_spike:
            positives.append("حجم تداول أعلى من المتوسط (تأكيد حركة).")

        # Distance to resistance/support
        if support is not None and close > 0:
            dist_sup = (close - support) / close * 100
            if dist_sup < 2.0:
                negatives.append("السعر قريب جدًا من الدعم — أي كسر بسيط قد يغير الصورة.")
            signals["dist_support_pct"] = float(dist_sup)

        if resistance is not None and close > 0:
            dist_res = (resistance - close) / close * 100
            if dist_res < 2.5:
                negatives.append("السعر قريب من مقاومة — قد يحتاج تأكيد اختراق.")
            signals["dist_resistance_pct"] = float(dist_res)

        # -------- Score & Confidence --------
        # base score from signals
        score = 50.0
        score += 10.0 if trend_up else (-10.0 if trend_dn else 0.0)
        score += 6.0 if macd_cross_up else (-6.0 if macd_cross_dn else 0.0)
        score += 5.0 if (rsi14 <= 35) else (-4.0 if (rsi14 >= 70) else 0.0)
        score += 4.0 if vol_spike else 0.0

        # weights learning
        score += (_get_weight("trend_up", 1.0) - 1.0) * (8.0 if trend_up else 0.0)
        score += (_get_weight("macd_cross_up", 1.0) - 1.0) * (6.0 if macd_cross_up else 0.0)

        # clamp
        score = max(0.0, min(100.0, score))

        # confidence: stable trend + confirmations
        conf = 45.0
        conf += 20.0 if trend_up or trend_dn else 0.0
        conf += 10.0 if (macd_cross_up or macd_cross_dn) else 0.0
        conf += 8.0 if vol_spike else 0.0
        conf += 6.0 if (support is not None and resistance is not None) else 0.0
        conf = max(0.0, min(100.0, conf))

        # -------- Risk gates --------
        risk_gates = []

        # Gate: trend not against the trade (for buy)
        gate_trend_ok = bool(trend_up or (not trend_dn))
        risk_gates.append({
            "gate": "Trend Gate",
            "status": "pass" if gate_trend_ok else "fail",
            "note": "الاتجاه ليس هابطًا قويًا (أو صاعد)."
        })

        # Gate: stop distance reasonable
        stop = close - 1.8 * atr14
        stop = float(max(stop, 0.0))
        stop_dist_pct = ((close - stop) / close * 100) if close else 0.0
        gate_stop_ok = stop_dist_pct <= 8.0  # مخاطرة معقولة
        risk_gates.append({
            "gate": "Risk/Stop Gate",
            "status": "pass" if gate_stop_ok else "fail",
            "note": f"نسبة مخاطرة تقريبًا {stop_dist_pct:.1f}% (كلما كانت أقل كان أفضل)."
        })

        # Gate: resistance too close
        gate_room = True
        if resistance is not None and close > 0:
            room_pct = (resistance - close) / close * 100
            gate_room = room_pct >= 2.0
            risk_gates.append({
                "gate": "Room to Resistance",
                "status": "pass" if gate_room else "warn",
                "note": f"المسافة للمقاومة {room_pct:.1f}%."
            })

        # -------- Recommendation --------
        # baseline
        if score >= 68 and gate_trend_ok and gate_stop_ok:
            rec = "شراء / تجميع"
            color = "#0ea5e9"
        elif score <= 38 and trend_dn:
            rec = "تخفيف / خروج"
            color = "#ef4444"
        else:
            rec = "انتظار / مراقبة"
            color = "#f59e0b"

        # -------- Entry / Targets / RR --------
        entry_zone = None
        entry_note = ""
        if support is not None:
            # entry near support or after break resistance
            entry_zone = [round(max(support, close - 0.6 * atr14), 2), round(min(close, close + 0.3 * atr14), 2)]
            entry_note = "منطقة دخول مقترحة قريبة من الدعم/السعر الحالي مع مراعاة التأكيد."

        # targets: T1 near resistance, T2 swing_high, T3 extension
        targets = []
        t1 = resistance if resistance is not None else close + 1.5 * atr14
        t2 = swing_high if np.isfinite(swing_high) else close + 2.5 * atr14
        t3 = max(t2, close + 3.5 * atr14)

        for i, tp in enumerate([t1, t2, t3], start=1):
            tp = float(tp)
            rr = ((tp - close) / (close - stop)) if (close > stop and close > 0) else None
            targets.append({
                "name": f"T{i}",
                "price": round(tp, 2),
                "rr": round(rr, 2) if rr is not None and np.isfinite(rr) else None
            })

        rr_main = targets[0]["rr"] if targets and targets[0].get("rr") is not None else None

        # -------- Scenarios --------
        # probabilities simplified by confidence & trend
        bull_p = min(0.55, 0.25 + conf/200.0 + (0.10 if trend_up else 0.0))
        bear_p = min(0.50, 0.20 + (0.15 if trend_dn else 0.0) + (0.10 if rsi14 >= 70 else 0.0))
        base_p = max(0.10, 1.0 - bull_p - bear_p)
        # normalize
        ssum = bull_p + base_p + bear_p
        bull_p, base_p, bear_p = bull_p/ssum, base_p/ssum, bear_p/ssum

        scenarios = [
            {
                "name": "Bull",
                "probability": round(bull_p*100, 1),
                "plan": "اختراق/ثبات فوق المقاومة مع حجم → استهداف T2 ثم T3.",
                "stop": round(stop, 2),
                "targets": [targets[1], targets[2]] if len(targets) >= 3 else targets,
            },
            {
                "name": "Base",
                "probability": round(base_p*100, 1),
                "plan": "تذبذب داخل نطاق → صفقات قصيرة باتجاه T1 مع وقف واضح.",
                "stop": round(stop, 2),
                "targets": [targets[0]],
            },
            {
                "name": "Bear",
                "probability": round(bear_p*100, 1),
                "plan": "كسر الدعم/ضعف زخم → تقليل تعرض أو انتظار إعادة بناء.",
                "stop": round(stop, 2),
                "targets": [],
            }
        ]

        # -------- Apply user rules --------
        user_rules = load_user_rules(enabled_only=True, max_rows=10) or []
        user_reasons = []
        user_feats = {}
        score_adj = 0.0
        for r in user_rules:
            ok, delta, reason, feats = _eval_user_rule(r.get("parsed"), df, ind)
            if ok:
                score_adj += float(delta)
                user_reasons.append(reason)
                user_feats.update(feats or {})

        if score_adj != 0:
            score = max(0.0, min(100.0, score + score_adj))
            conf = max(0.0, min(100.0, conf + (6.0 if score_adj > 0 else 3.0)))

            if score_adj > 0:
                positives.append("قاعدة المستخدم أعطت تعزيزًا لإشارة الدخول.")
            else:
                negatives.append("قاعدة المستخدم أعطت تحذيرًا/ميل للخروج.")

        # -------- Build summary text (سبب التوصية كنص واحد مرتب) --------
        # concise but clear
        bullets = []
        if positives:
            bullets.append("✅ عوامل داعمة: " + " | ".join(positives[:3]))
        if negatives:
            bullets.append("⚠️ عوامل مخاطرة: " + " | ".join(negatives[:3]))
        bullets.append(f"🎯 الخطة: دخول {('ضمن ' + str(entry_zone)) if entry_zone else 'بعد تأكيد'} | وقف {round(stop,2)} | هدف أول {targets[0]['price'] if targets else '-'}")
        if user_reasons:
            bullets.append("🧠 قواعدك: " + " | ".join(user_reasons[:2]))

        summary_text = "\n".join(bullets)

        # -------- Features for logging --------
        features = {}
        features.update({k: int(v) if isinstance(v, (bool, np.bool_)) else v for k, v in signals.items()})
        features.update(user_feats)

        horizon_days = _tf_horizon_days(tf)
        report = {
            "recommendation": rec,
            "color": color,
            "strategy": "Osoli Advisor",
            "score": round(float(score), 1),
            "confidence": int(round(float(conf))),
            "confidence_label": ("عالية" if conf >= 70 else "متوسطة" if conf >= 50 else "منخفضة"),
            "summary_text": summary_text,

            "entry": {
                "entry_zone": entry_zone,
                "entry_note": entry_note,
            },
            "risk": {
                "stop": round(stop, 2),
                "invalidation": (round(support, 2) if support is not None else None),
                "rr": rr_main
            },
            "targets": targets,
            "scenarios": scenarios,

            "evidence": {
                "positives": positives,
                "negatives": negatives,
                "signals": signals,
                "notes": notes,
            },
            "risk_gates": risk_gates,

            "levels": {
                "support": round(support, 2) if support is not None else None,
                "resistance": round(resistance, 2) if resistance is not None else None,
                "fib382": round(fib382, 2) if np.isfinite(fib382) else None,
                "fib50": round(fib50, 2) if np.isfinite(fib50) else None,
                "fib618": round(fib618, 2) if np.isfinite(fib618) else None,
                "swing_high": round(swing_high, 2) if np.isfinite(swing_high) else None,
                "swing_low": round(swing_low, 2) if np.isfinite(swing_low) else None,
            },
            "meta": {
                "symbol": sym,
                "timeframe": tf,
                "as_of": _now_str(),
                "engine_version": AI_ENGINE_VERSION,
                "horizon_days": horizon_days,
                "close": round(close, 2),
            }
        }

        # log (best effort)
        try:
            log_ai_signal(sym, tf, features, report, horizon_days=horizon_days)
        except Exception:
            pass

        return report

    except Exception as e:
        return {
            "__error__": "exception",
            "__trace__": traceback.format_exc(),
            "symbol": symbol,
            "timeframe": timeframe,
            "reason": str(e)
        }


# ============================================================
# Portfolio Risk Score (0-100)
# ============================================================
def calculate_portfolio_risk_score(trades_df: pd.DataFrame, cash_pct: float):
    """
    مبسط وثابت:
    - أقل كاش => مخاطرة أعلى
    - تركّز عالي في سهم واحد => مخاطرة أعلى
    - عدد صفقات مفتوحة كبير => مخاطرة أعلى
    """
    try:
        score = 35.0

        # cash gate
        if cash_pct <= 5:
            score += 25
        elif cash_pct <= 10:
            score += 15
        elif cash_pct <= 20:
            score += 8
        else:
            score -= 5

        df = trades_df if isinstance(trades_df, pd.DataFrame) else pd.DataFrame()
        if df.empty:
            return int(max(0, min(100, score)))

        if "status" in df.columns:
            s = df["status"].astype(str).str.strip().str.lower()
            df = df[s == "open"].copy()

        # open count
        n = len(df)
        if n >= 12:
            score += 18
        elif n >= 8:
            score += 12
        elif n >= 5:
            score += 6

        # concentration
        if "market_value" in df.columns:
            mv = pd.to_numeric(df["market_value"], errors="coerce").fillna(0.0)
            total = float(mv.sum())
            if total > 0:
                wmax = float((mv / total).max())
                if wmax >= 0.40:
                    score += 20
                elif wmax >= 0.30:
                    score += 12
                elif wmax >= 0.25:
                    score += 8

        return int(max(0, min(100, score)))
    except Exception:
        return 50


# ============================================================
# Stress Test
# ============================================================
def run_stress_test(portfolio_value: float, open_positions_df: pd.DataFrame):
    """
    يعيد:
    { scenarios: [{scenario, impact_pct, impact_value}], insight: "..." }
    """
    try:
        pv = float(portfolio_value or 0)
        if pv <= 0:
            return {"scenarios": [], "insight": "لا توجد قيمة محفظة مفتوحة للاختبار."}

        scenarios = [
            ("هبوط سوق -5%", -5),
            ("هبوط سوق -10%", -10),
            ("هبوط سوق -15%", -15),
            ("صدمة قوية -25%", -25),
        ]

        out = []
        for name, pct in scenarios:
            impact_value = pv * (pct / 100.0)
            out.append({
                "scenario": name,
                "impact_pct": pct,
                "impact_value": round(impact_value, 2)
            })

        insight = "كلما زاد التعرض للأسهم (وقل الكاش)، زادت حساسية المحفظة للهبوط."
        return {"scenarios": out, "insight": insight}
    except Exception:
        return {"scenarios": [], "insight": ""}


# ============================================================
# Rebalancing Suggestions
# ============================================================
def generate_rebalancing_suggestions(trades_df: pd.DataFrame, cash_pct: float):
    """
    يعيد قائمة نصائح بسيطة لإعادة التوازن.
    """
    tips = []
    try:
        df = trades_df if isinstance(trades_df, pd.DataFrame) else pd.DataFrame()
        if df.empty:
            return tips

        if "status" in df.columns:
            s = df["status"].astype(str).str.strip().str.lower()
            df = df[s == "open"].copy()

        if df.empty:
            return tips

        if cash_pct < 10:
            tips.append("رفع الكاش إلى 10%+ لتقليل ضغط التقلبات.")

        if "market_value" in df.columns and "symbol" in df.columns:
            mv = pd.to_numeric(df["market_value"], errors="coerce").fillna(0.0)
            total = float(mv.sum())
            if total > 0:
                w = mv / total
                df2 = df.copy()
                df2["weight"] = w
                heavy = df2.sort_values("weight", ascending=False).head(3)
                for _, r in heavy.iterrows():
                    if float(r.get("weight", 0)) >= 0.30:
                        tips.append(f"تقليل تركّز {r.get('symbol')} (وزن {float(r.get('weight'))*100:.1f}%).")

        if len(df) >= 10:
            tips.append("عدد المراكز المفتوحة كبير — تأكد من تحديد حد أقصى للمراكز حسب حجم المحفظة.")

        return tips
    except Exception:
        return tips