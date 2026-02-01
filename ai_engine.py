# ai_engine.py
import json
import re
import uuid
import traceback
import pandas as pd
import numpy as np
from datetime import datetime


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
    - Postgres placeholders: %s
    - SQLite placeholders: ?
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

    # فك MultiIndex الأعمدة (أحياناً من yfinance)
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


def _clip01(x):
    try:
        x = float(x)
    except Exception:
        return 0.0
    return max(0.0, min(1.0, x))


# ============================================================
# ✅ Cross-DB table schemas (SQLite/Postgres)
# ============================================================
def _ensure_ai_tables():
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False

    ok1 = _try_exec(
        """
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
        """,
        (),
    )

    ok2 = _try_exec(
        """
        CREATE TABLE IF NOT EXISTS ai_weights (
            key TEXT PRIMARY KEY,
            weight REAL DEFAULT 1.0,
            updated_at TEXT
        )
        """,
        (),
    )

    return bool(ok1 and ok2)


def _ensure_user_rules_table():
    ok = _try_exec(
        """
        CREATE TABLE IF NOT EXISTS ai_user_rules (
            id TEXT PRIMARY KEY,
            created_at TEXT,
            title TEXT,
            rule_text TEXT,
            parsed_json TEXT,
            enabled INTEGER DEFAULT 1
        )
        """,
        (),
    )
    return bool(ok)


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
# Weights (Online learning)
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
            (str(key), float(weight), _now_str()),
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
def save_user_rule(rule_text: str, title: str = None, enabled: int = 1):
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return {"ok": False, "reason": "DB not available"}

    _ensure_user_rules_table()
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
    _ensure_user_rules_table()
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

            rules.append(
                {
                    "id": r.get("id"),
                    "title": r.get("title") or "قاعدة مستخدم",
                    "rule_text": r.get("rule_text") or "",
                    "parsed": parsed,
                }
            )
        return rules
    except Exception:
        return []


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

    if "فيبو" in t or "fibo" in t or "fib" in t:
        if "38" in t:
            if any(k in t for k in ["اختراق", "فوق", "اعلى"]):
                parsed["conditions"].append({"type": "fib_cross", "value": 38})
                parsed["tags"].append("FIB_38_UP")
            if any(k in t for k in ["كسر", "تحت", "اسفل"]):
                parsed["conditions"].append({"type": "fib_cross", "value": -38})
                parsed["tags"].append("FIB_38_DN")

    m = re.search(r"(?:boost|قوة|تأثير)\s*[:=]?\s*(\d+(?:\.\d+)?)", t)
    if m:
        parsed["boost"] = float(m.group(1))

    return parsed


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

    fib382 = ind.get("fib382", None)

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

        if t == "fib_cross" and fib382 is not None:
            if int(v) == 38:
                return close > float(fib382) and prev_close <= float(fib382)
            if int(v) == -38:
                return close < float(fib382) and prev_close >= float(fib382)

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
# Indicators
# ============================================================
def _atr14(df: pd.DataFrame) -> pd.Series:
    high = df["High"].astype(float)
    low = df["Low"].astype(float)
    close = df["Close"].astype(float)

    prev_close = close.shift(1)
    tr = pd.concat(
        [
            (high - low),
            (high - prev_close).abs(),
            (low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    return tr.rolling(14).mean().bfill()


def _compute_fib382(df: pd.DataFrame, lookback=120):
    if df is None or df.empty or len(df) < 30:
        return None
    d = df.tail(int(lookback))
    hi = float(d["High"].max())
    lo = float(d["Low"].min())
    if hi <= lo:
        return None
    # 38.2 retracement from low -> high
    return lo + (hi - lo) * 0.382


def _compute_indicators(df: pd.DataFrame):
    out = {}
    if df is None or df.empty or len(df) < 60:
        return out

    close = df["Close"].astype(float)
    vol = df["Volume"].astype(float) if "Volume" in df.columns else pd.Series([0] * len(df), index=df.index)

    out["sma20"] = close.rolling(20).mean()
    out["sma50"] = close.rolling(50).mean()
    out["sma200"] = close.rolling(200).mean()

    # RSI 14
    delta = close.diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = (-delta.clip(upper=0)).rolling(14).mean()
    rs = gain / (loss.replace(0, np.nan))
    rsi = 100 - (100 / (1 + rs))
    out["rsi14"] = rsi.bfill().fillna(50)

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    hist = macd - signal
    out["macd"] = macd
    out["macd_signal"] = signal
    out["macd_hist"] = hist

    # ATR
    out["atr14"] = _atr14(df)

    # Volume avg
    out["vol_ma20"] = vol.rolling(20).mean().bfill()

    # Fib 38.2 level (number)
    out["fib382"] = _compute_fib382(df)

    return out


# ============================================================
# Feature extraction + scoring
# ============================================================
def _extract_features(df: pd.DataFrame, ind: dict) -> dict:
    feats = {}
    if df is None or df.empty or len(df) < 60:
        return feats

    close = float(df["Close"].iloc[-1])
    prev_close = float(df["Close"].iloc[-2])

    sma20 = float(ind["sma20"].iloc[-1]) if "sma20" in ind and isinstance(ind["sma20"], pd.Series) else None
    sma50 = float(ind["sma50"].iloc[-1]) if "sma50" in ind and isinstance(ind["sma50"], pd.Series) else None
    sma200 = float(ind["sma200"].iloc[-1]) if "sma200" in ind and isinstance(ind["sma200"], pd.Series) else None

    rsi = float(ind["rsi14"].iloc[-1]) if "rsi14" in ind and isinstance(ind["rsi14"], pd.Series) else 50.0

    macd = float(ind["macd"].iloc[-1]) if "macd" in ind and isinstance(ind["macd"], pd.Series) else 0.0
    macd_prev = float(ind["macd"].iloc[-2]) if "macd" in ind and isinstance(ind["macd"], pd.Series) and len(ind["macd"]) > 2 else macd
    sig = float(ind["macd_signal"].iloc[-1]) if "macd_signal" in ind and isinstance(ind["macd_signal"], pd.Series) else 0.0
    sig_prev = float(ind["macd_signal"].iloc[-2]) if "macd_signal" in ind and isinstance(ind["macd_signal"], pd.Series) and len(ind["macd_signal"]) > 2 else sig

    atr = float(ind["atr14"].iloc[-1]) if "atr14" in ind and isinstance(ind["atr14"], pd.Series) else 0.0
    vol_ma20 = float(ind["vol_ma20"].iloc[-1]) if "vol_ma20" in ind and isinstance(ind["vol_ma20"], pd.Series) else 0.0
    vol_now = float(df["Volume"].iloc[-1]) if "Volume" in df.columns else 0.0

    fib382 = ind.get("fib382", None)
    fib382 = float(fib382) if fib382 is not None else None

    # Trend regime
    if sma50 and sma200:
        feats["trend_up"] = int(sma50 > sma200)
        feats["trend_down"] = int(sma50 < sma200)

    # Price vs moving averages
    if sma20:
        feats["close_above_sma20"] = int(close > sma20)
        feats["cross_up_sma20"] = int(close > sma20 and prev_close <= sma20)
        feats["cross_dn_sma20"] = int(close < sma20 and prev_close >= sma20)
    if sma50:
        feats["close_above_sma50"] = int(close > sma50)
        feats["cross_up_sma50"] = int(close > sma50 and prev_close <= sma50)
        feats["cross_dn_sma50"] = int(close < sma50 and prev_close >= sma50)
    if sma200:
        feats["close_above_sma200"] = int(close > sma200)

    # RSI zones
    feats["rsi_overbought"] = int(rsi >= 70)
    feats["rsi_oversold"] = int(rsi <= 30)
    feats["rsi_mid_up"] = int(rsi >= 50)

    # MACD crosses + above/below zero
    feats["macd_cross_up"] = int(macd > sig and macd_prev <= sig_prev)
    feats["macd_cross_dn"] = int(macd < sig and macd_prev >= sig_prev)
    feats["macd_above_zero"] = int(macd > 0)
    feats["macd_below_zero"] = int(macd < 0)

    # Vol spike
    if vol_ma20 and vol_ma20 > 0:
        feats["vol_spike"] = int((vol_now / vol_ma20) >= 1.8)
    else:
        feats["vol_spike"] = 0

    # Fib interaction (simple)
    if fib382 is not None:
        feats["close_above_fib382"] = int(close > fib382)
        feats["cross_up_fib382"] = int(close > fib382 and prev_close <= fib382)
        feats["cross_dn_fib382"] = int(close < fib382 and prev_close >= fib382)

    # Volatility flag
    if atr and close > 0:
        feats["atr_high"] = int((atr / close) >= 0.04)  # 4% ATR as a rough flag

    return feats


def _score_features(features: dict) -> dict:
    """
    نطلع:
    - score_raw: مجموع feature * weight
    - positives/negatives list for explainability
    """
    pos = []
    neg = []
    score = 0.0

    # تعريف تأثير كل feature (علامة + أو -)
    # (نخليها بسيطة الآن، والأوزان تتعلم من DB)
    impacts = {
        "trend_up": +1.2,
        "trend_down": -1.2,
        "close_above_sma50": +0.8,
        "close_above_sma200": +0.8,
        "cross_up_sma20": +0.7,
        "cross_dn_sma20": -0.7,
        "macd_cross_up": +0.9,
        "macd_cross_dn": -0.9,
        "macd_above_zero": +0.4,
        "macd_below_zero": -0.4,
        "rsi_mid_up": +0.4,
        "rsi_overbought": -0.3,   # تحذير
        "rsi_oversold": +0.3,     # ارتداد محتمل
        "vol_spike": +0.35,
        "atr_high": -0.35,        # مخاطرة أعلى
        "cross_up_fib382": +0.3,
        "cross_dn_fib382": -0.3,
        "close_above_fib382": +0.15,
    }

    for k, v in (features or {}).items():
        if not (isinstance(v, (int, bool)) and int(v) in (0, 1)):
            continue
        if int(v) == 0:
            continue

        base = impacts.get(k, 0.0)
        w = _get_weight(k, 1.0)
        contrib = base * float(w)
        score += contrib

        if contrib >= 0.15:
            pos.append(f"{k} (+{contrib:.2f})")
        elif contrib <= -0.15:
            neg.append(f"{k} ({contrib:.2f})")

    return {"score_raw": float(score), "positives": pos, "negatives": neg}


def _score_to_recommendation(score_raw: float):
    # نطاقات بسيطة
    if score_raw >= 1.8:
        return "شراء / إيجابي", "Bullish", "#16a34a"
    if score_raw >= 0.7:
        return "مراقبة إيجابية", "Leaning Bullish", "#22c55e"
    if score_raw <= -1.8:
        return "تجنب / سلبي", "Bearish", "#dc2626"
    if score_raw <= -0.7:
        return "مراقبة سلبية", "Leaning Bearish", "#f97316"
    return "محايد", "Neutral", "#667085"


def _confidence_from_evidence(pos_count: int, neg_count: int, score_raw: float):
    # ثقة تقريبية من قوة الإشارة وتوازن الأدلة
    strength = min(1.0, abs(score_raw) / 3.0)  # 0..1
    balance = 1.0 - (min(pos_count, neg_count) / max(1, (pos_count + neg_count)))  # كلما زاد التضارب تقل
    conf = 35 + 55 * (0.55 * strength + 0.45 * balance)
    conf = int(max(0, min(100, conf)))
    return conf


# ============================================================
# Risk gates + scenarios
# ============================================================
def _build_risk_gates(df: pd.DataFrame, ind: dict, timeframe: str) -> dict:
    """
    بوابات مخاطرة بسيطة:
    - بيانات كافية
    - تقلب عالي
    - اتجاه ضد الصفقة
    """
    gates = {"pass": True, "reasons": []}

    if df is None or df.empty or len(df) < 80:
        gates["pass"] = False
        gates["reasons"].append("بيانات غير كافية (يحتاج تاريخ أطول).")
        return gates

    close = float(df["Close"].iloc[-1])
    atr = float(ind["atr14"].iloc[-1]) if "atr14" in ind and isinstance(ind["atr14"], pd.Series) else 0.0
    if close > 0 and atr / close >= 0.06:
        gates["reasons"].append("تقلب مرتفع (ATR كبير) — خفّض حجم الصفقة أو انتظر تهدئة.")
    if timeframe in ("1h", "30m", "15m"):
        gates["reasons"].append("الفاصل لحظي/قصير — الإشارات أسرع وتحتاج انضباط وقف خسارة.")

    return gates


def _support_resistance(df: pd.DataFrame, lookback=60):
    d = df.tail(int(lookback))
    sup = float(d["Low"].min()) if not d.empty else None
    res = float(d["High"].max()) if not d.empty else None
    return sup, res


def _build_scenarios(df: pd.DataFrame, ind: dict, score_raw: float):
    """
    سيناريوهات مبسطة مع Entry/Stop/Targets اعتماداً على ATR + S/R
    """
    scenarios = []
    if df is None or df.empty:
        return scenarios

    close = float(df["Close"].iloc[-1])
    atr = float(ind["atr14"].iloc[-1]) if "atr14" in ind and isinstance(ind["atr14"], pd.Series) else 0.0
    sup, res = _support_resistance(df, lookback=60)

    # default
    atr = atr if atr and atr > 0 else max(0.01, close * 0.02)

    # Bullish scenario
    if score_raw >= 0.7:
        entry = close
        stop = max(0.0, (sup if sup else close - 1.5 * atr), close - 2.0 * atr)
        target1 = (res if res else close + 2.0 * atr)
        target2 = close + 3.5 * atr
        scenarios.append(
            {
                "name": "سيناريو صعود",
                "trigger": "استمرار الإشارات الإيجابية + ثبات فوق المتوسطات",
                "entry": entry,
                "stop": stop,
                "target1": target1,
                "target2": target2,
                "note": "ارفع الوقف تدريجياً إذا تحقق الهدف 1.",
            }
        )

    # Bearish scenario
    if score_raw <= -0.7:
        entry = close
        stop = (res if res else close + 1.5 * atr)
        target1 = (sup if sup else close - 2.0 * atr)
        target2 = close - 3.5 * atr
        scenarios.append(
            {
                "name": "سيناريو هبوط/خروج",
                "trigger": "ظهور إشارات سلبية/كسر متوسطات",
                "entry": entry,
                "stop": stop,
                "target1": target1,
                "target2": target2,
                "note": "هذا السيناريو مناسب كخطة خروج/تحوّط وليس دعوة للبيع الإجباري.",
            }
        )

    # Neutral scenario (range)
    if -0.7 < score_raw < 0.7:
        entry = close
        stop = max(0.0, close - 1.8 * atr)
        target1 = close + 1.8 * atr
        scenarios.append(
            {
                "name": "سيناريو تذبذب",
                "trigger": "لا يوجد اتجاه واضح — تداول نطاق",
                "entry": entry,
                "stop": stop,
                "target1": target1,
                "target2": None,
                "note": "يفضل انتظار كسر واضح/تقاطع قوي قبل قرار كبير.",
            }
        )

    return scenarios[:6]


# ============================================================
# Public API expected by views.py
# ============================================================
def generate_ai_report(symbol, timeframe="1d"):
    """
    يرجّع dict منظم يناسب views.py:
    recommendation, strategy, color, confidence, top_evidence, top_risks,
    risk_gates, scenarios, notes, explainability
    """
    try:
        symbol = _normalize_symbol(symbol)

        # جلب البيانات السعرية من market_data
        try:
            from market_data import get_chart_history
        except Exception as e:
            return {"__error__": "market_data missing", "__trace__": repr(e)}

        # timeframe mapping to interval (بشكل بسيط)
        interval = timeframe
        # period مناسب للإشارات (نزيده لو أسبوعي/شهري)
        if timeframe == "1mo":
            period = "10y"
        elif timeframe == "1wk":
            period = "5y"
        else:
            period = "2y"

        try:
            df = get_chart_history(symbol, period=period, interval=interval)
        except TypeError:
            # fallback لو الدالة ما تدعم interval
            df = get_chart_history(symbol, period)

        if not isinstance(df, pd.DataFrame):
            df = pd.DataFrame(df)

        df = _ensure_ohlcv_columns(df)
        if df is None or df.empty or len(df) < 80:
            return {
                "recommendation": "غير كافٍ",
                "strategy": "Data Insufficient",
                "color": "#667085",
                "confidence": 15,
                "top_evidence": [],
                "top_risks": ["بيانات غير كافية لتوليد تقرير موثوق."],
                "risk_gates": {"pass": False, "reasons": ["بيانات غير كافية (جرّب فترة أطول)."]},
                "scenarios": [],
                "notes": [],
                "explainability": {"positives": [], "negatives": [], "notes": []},
            }

        ind = _compute_indicators(df)
        feats = _extract_features(df, ind)
        scored = _score_features(feats)

        score_raw = float(scored.get("score_raw", 0.0))
        recommendation, strategy, color = _score_to_recommendation(score_raw)

        # تطبيق قواعد المستخدم (لو موجودة)
        user_notes = []
        try:
            rules = load_user_rules(enabled_only=True, max_rows=50) or []
        except Exception:
            rules = []

        # نسمح بتأثير قاعدة/قاعدتين كحد أقصى لمنع التلاعب
        applied_count = 0
        for r in rules[:10]:
            ok, delta, reason, extra_feats = _eval_user_rule(r.get("parsed") or {}, df, ind)
            if ok:
                score_raw += float(delta)
                applied_count += 1
                user_notes.append(reason)
                # سجل كfeatures binary للـ learning
                for k, v in (extra_feats or {}).items():
                    feats[k] = v
                if applied_count >= 2:
                    break

        # إعادة توليد بعد القواعد
        recommendation, strategy, color = _score_to_recommendation(score_raw)

        pos = scored.get("positives", [])
        neg = scored.get("negatives", [])
        conf = _confidence_from_evidence(len(pos), len(neg), score_raw)

        gates = _build_risk_gates(df, ind, timeframe=timeframe)
        scenarios = _build_scenarios(df, ind, score_raw=score_raw)

        # top evidence/risks
        top_evidence = [x.replace("_", " ") for x in pos[:8]]
        top_risks = [x.replace("_", " ") for x in neg[:8]]

        # ملاحظات تلقائية
        notes = []
        if user_notes:
            notes.extend(user_notes)
        if gates.get("reasons"):
            notes.extend([f"🛡️ {x}" for x in gates["reasons"][:6]])

        rep = {
            "recommendation": recommendation,
            "strategy": strategy,
            "color": color,
            "confidence": conf,
            "top_evidence": top_evidence,
            "top_risks": top_risks,
            "risk_gates": gates,
            "scenarios": scenarios,
            "notes": notes,
            "explainability": {
                "positives": top_evidence,
                "negatives": top_risks,
                "notes": notes[:12],
            },
        }

        # log
        try:
            log_ai_signal(symbol, timeframe, feats, rep, horizon_days=20, sector=None, strategy_name=strategy)
        except Exception:
            pass

        return rep

    except Exception:
        return {"__error__": "generate_ai_report failed", "__trace__": traceback.format_exc()}


def calculate_portfolio_risk_score(trades_df: pd.DataFrame, cash_pct: float) -> int:
    """
    0 (أفضل) -> 100 (أسوأ)
    عوامل بسيطة:
    - تركّز المحفظة (أكبر مركز)
    - نسبة الكاش (كلما زاد الكاش تقل المخاطرة)
    - عدد المراكز (أقل مراكز = مخاطرة تركّز أعلى)
    """
    try:
        cash_pct = float(cash_pct or 0)
    except Exception:
        cash_pct = 0.0

    if trades_df is None or not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
        # محفظة فاضية = مخاطرة قليلة
        return int(max(0, min(100, 15 - 0.2 * cash_pct)))

    df = trades_df.copy()
    if "status" in df.columns:
        st = df["status"].astype(str).str.lower().str.strip()
        df = df[st == "open"].copy()

    if df.empty:
        return int(max(0, min(100, 20 - 0.2 * cash_pct)))

    # weights
    if "market_value" in df.columns:
        mv = pd.to_numeric(df["market_value"], errors="coerce").fillna(0)
    else:
        # fallback: quantity * current/entry
        q = pd.to_numeric(df.get("quantity", 0), errors="coerce").fillna(0)
        p = pd.to_numeric(df.get("entry_price", 0), errors="coerce").fillna(0)
        mv = q * p

    total = float(mv.sum())
    if total <= 0:
        return int(max(0, min(100, 25 - 0.2 * cash_pct)))

    w = mv / total
    max_pos = float(w.max()) if len(w) else 0.0
    npos = int(len(w))

    # base risk from concentration
    risk = 25 + 55 * max_pos  # max_pos=1 => +55
    if npos <= 2:
        risk += 10
    elif npos <= 5:
        risk += 5

    # cash reduces risk
    risk -= 0.35 * cash_pct

    return int(max(0, min(100, round(risk))))


def run_stress_test(portfolio_value: float, open_positions_df: pd.DataFrame):
    """
    يرجع سيناريوهات تأثير هبوط السوق/القطاعات بشكل مبسط.
    """
    try:
        pv = float(portfolio_value or 0)
    except Exception:
        pv = 0.0

    scenarios = []
    if pv <= 0:
        return {"scenarios": [], "insight": "لا توجد قيمة محفظة لحساب اختبار التحمل."}

    # افتراضات هبوط
    shocks = [
        ("هبوط خفيف", -5),
        ("هبوط متوسط", -10),
        ("هبوط قوي", -20),
    ]

    # تركّز افتراضي
    conc = 0.0
    try:
        if open_positions_df is not None and isinstance(open_positions_df, pd.DataFrame) and not open_positions_df.empty:
            if "market_value" in open_positions_df.columns:
                mv = pd.to_numeric(open_positions_df["market_value"], errors="coerce").fillna(0)
            else:
                q = pd.to_numeric(open_positions_df.get("quantity", 0), errors="coerce").fillna(0)
                p = pd.to_numeric(open_positions_df.get("entry_price", 0), errors="coerce").fillna(0)
                mv = q * p
            tot = float(mv.sum())
            if tot > 0:
                conc = float((mv / tot).max())
    except Exception:
        conc = 0.0

    for name, pct in shocks:
        impact_val = pv * (pct / 100.0)
        # نعاقب التركّز
        impact_pct = pct * (1.0 + 0.35 * conc)
        scenarios.append({"scenario": name, "impact_pct": float(impact_pct), "impact_value": float(pv * (impact_pct / 100.0))})

    insight = "كلما زاد تركّز أكبر مركز، زاد أثر الصدمات على المحفظة."
    return {"scenarios": scenarios, "insight": insight}


def generate_rebalancing_suggestions(trades_df: pd.DataFrame, cash_pct: float):
    """
    اقتراحات مبسطة:
    - لو تركّز عالي: خفّض أكبر مركز
    - لو كاش منخفض جداً: زد الكاش
    """
    sugg = []
    try:
        cash_pct = float(cash_pct or 0)
    except Exception:
        cash_pct = 0.0

    if trades_df is None or not isinstance(trades_df, pd.DataFrame) or trades_df.empty:
        return sugg

    df = trades_df.copy()
    if "status" in df.columns:
        st = df["status"].astype(str).str.lower().str.strip()
        df = df[st == "open"].copy()

    if df.empty:
        return sugg

    if "market_value" in df.columns:
        mv = pd.to_numeric(df["market_value"], errors="coerce").fillna(0)
    else:
        q = pd.to_numeric(df.get("quantity", 0), errors="coerce").fillna(0)
        p = pd.to_numeric(df.get("entry_price", 0), errors="coerce").fillna(0)
        mv = q * p

    total = float(mv.sum())
    if total <= 0:
        return sugg

    w = mv / total
    max_i = int(w.idxmax())
    max_w = float(w.loc[max_i])

    if max_w >= 0.35:
        sym = str(df.loc[max_i].get("symbol", ""))
        sugg.append({"type": "concentration", "text": f"تركيز مرتفع: أكبر مركز ({sym}) يمثل {max_w*100:.1f}%. فكر بتخفيفه أو موازنة مراكز أخرى."})

    if cash_pct < 5:
        sugg.append({"type": "cash", "text": f"نسبة الكاش منخفضة ({cash_pct:.1f}%). فكر برفعها لتقليل المخاطرة أو لاقتناص فرص."})
    elif cash_pct > 35:
        sugg.append({"type": "cash", "text": f"نسبة الكاش مرتفعة ({cash_pct:.1f}%). قد تكون فرصة لتوزيع تدريجي على فرص قوية (حسب إشاراتك)."})

    return sugg