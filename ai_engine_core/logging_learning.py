# ai_engine_core/logging_learning.py

import json
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

import pandas as pd

from .db import _safe_import_db, _try_exec, _ensure_ai_tables
from .core import _now_str


def _parse_dt(s: Any) -> Optional[datetime]:
    """Best-effort parse datetime stored as TEXT/TIMESTAMP."""
    if s is None:
        return None
    try:
        if isinstance(s, datetime):
            return s
        ss = str(s).strip()
        if not ss:
            return None
        # common formats
        try:
            return datetime.fromisoformat(ss.replace("Z", ""))
        except Exception:
            pass
        for fmt in (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d",
            "%Y/%m/%d",
            "%d/%m/%Y",
        ):
            try:
                return datetime.strptime(ss, fmt)
            except Exception:
                continue
        return None
    except Exception:
        return None


def _tf_interval(timeframe: str) -> str:
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


def evaluate_pending_outcomes(max_rows: int = 80, trading_bars: bool = True) -> Dict[str, Any]:
    """Evaluate past signals that have not been evaluated yet.

    Logic:
      - Pick ai_signals where outcome_return_pct is NULL
      - For each, fetch recent price history
      - Find entry close around created_at, then compute exit close after horizon bars
      - Update outcome_return_pct + outcome_win

    Notes:
      - Uses bar counting (more stable than calendar days).
      - Works for both sqlite/postgres.
    """
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()

    try:
        df = fetch_table("ai_signals")
        if df is None or df.empty:
            return {"ok": True, "evaluated": 0, "skipped": 0, "errors": 0, "details": []}

        # pending only
        if "outcome_return_pct" in df.columns:
            dfp = df[df["outcome_return_pct"].isna()]
        else:
            dfp = df

        if dfp.empty:
            return {"ok": True, "evaluated": 0, "skipped": 0, "errors": 0, "details": []}

        # newest first
        if "created_at" in dfp.columns:
            dfp = dfp.sort_values("created_at", ascending=True)

        dfp = dfp.head(int(max_rows))

        from market_data import get_chart_history  # local import

        evaluated = 0
        skipped = 0
        errors = 0
        details = []

        for _, r in dfp.iterrows():
            try:
                sid = str(r.get("id") or "").strip()
                symbol = str(r.get("symbol") or "").strip()
                tf = str(r.get("timeframe") or "1D")
                horizon = int(r.get("horizon_days") or 20)
                created_at = _parse_dt(r.get("created_at"))
                if not sid or not symbol or created_at is None:
                    skipped += 1
                    continue

                # Entry close: prefer stored feature close
                entry_close = None
                try:
                    feats = json.loads(r.get("features_json") or "{}")
                    if isinstance(feats, dict) and feats.get("close") is not None:
                        entry_close = float(feats.get("close"))
                except Exception:
                    entry_close = None

                interval = _tf_interval(tf)

                # Fetch enough history (best-effort)
                # 6mo is usually enough for 20D horizon even with gaps
                try:
                    hist = get_chart_history(symbol, period="6mo", interval=interval)
                except TypeError:
                    hist = get_chart_history(symbol, "6mo")

                if hist is None or getattr(hist, "empty", False):
                    skipped += 1
                    continue

                # normalize index
                try:
                    h = hist.copy()
                    if not isinstance(h.index, type(getattr(h, "index", None))):
                        pass
                    # Make index datetime
                    if not hasattr(h.index, "to_pydatetime"):
                        # already not datetime-like
                        h.index = pd.to_datetime(h.index, errors="coerce")
                    else:
                        h.index = pd.to_datetime(h.index, errors="coerce")
                    h = h.dropna(subset=["Close"], how="any")
                except Exception:
                    skipped += 1
                    continue

                # Find entry bar
                entry_idx = None
                try:
                    # created_at date match: choose first bar >= created_at
                    mask = h.index >= created_at
                    if mask.any():
                        entry_idx = int(mask.argmax())
                    else:
                        # if created_at is in future or history doesn't cover, use last
                        entry_idx = max(len(h) - 1, 0)
                except Exception:
                    entry_idx = None

                if entry_idx is None or entry_idx < 0 or entry_idx >= len(h):
                    skipped += 1
                    continue

                if entry_close is None:
                    try:
                        entry_close = float(h["Close"].iloc[entry_idx])
                    except Exception:
                        skipped += 1
                        continue

                exit_idx = entry_idx + int(horizon)
                if exit_idx >= len(h):
                    # not enough bars yet
                    skipped += 1
                    continue

                try:
                    exit_close = float(h["Close"].iloc[exit_idx])
                except Exception:
                    skipped += 1
                    continue

                ret_pct = ((exit_close / entry_close) - 1.0) * 100.0
                ok = update_ai_outcome(sid, float(ret_pct), exit_features={"exit_close": exit_close})
                if ok:
                    evaluated += 1
                    details.append({"id": sid, "symbol": symbol, "tf": tf, "horizon": horizon, "ret_pct": round(ret_pct, 3)})
                else:
                    errors += 1

            except Exception:
                errors += 1

        return {"ok": True, "evaluated": evaluated, "skipped": skipped, "errors": errors, "details": details[:20]}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


def get_calibration_snapshot(symbol: Optional[str] = None, timeframe: Optional[str] = None, max_rows: int = 500) -> Dict[str, Any]:
    """Return simple calibration stats from evaluated history."""
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()
    try:
        df = fetch_table("ai_signals")
        if df is None or df.empty:
            return {"ok": False, "reason": "no history"}

        if "outcome_return_pct" not in df.columns:
            return {"ok": False, "reason": "missing outcome"}

        df = df.dropna(subset=["outcome_return_pct"])
        if df.empty:
            return {"ok": False, "reason": "no evaluated rows"}

        if symbol:
            df = df[df["symbol"].astype(str) == str(symbol)]
        if timeframe:
            df = df[df["timeframe"].astype(str) == str(timeframe)]

        if df.empty:
            return {"ok": False, "reason": "no matching rows"}

        if "created_at" in df.columns:
            df = df.sort_values("created_at", ascending=False)
        df = df.head(int(max_rows))

        # Extract recommendation + confidence from report_json
        rec_counts = {}
        conf_bins = {"0-39": [], "40-59": [], "60-79": [], "80-100": []}
        for _, r in df.iterrows():
            try:
                rep = json.loads(r.get("report_json") or "{}")
            except Exception:
                rep = {}
            rec = str(rep.get("recommendation") or "").strip() or "(غير محدد)"
            rec_counts.setdefault(rec, {"n": 0, "avg_ret": 0.0, "wins": 0})
            rec_counts[rec]["n"] += 1
            ret = float(r.get("outcome_return_pct") or 0.0)
            rec_counts[rec]["avg_ret"] += ret
            rec_counts[rec]["wins"] += 1 if ret > 0 else 0

            conf = rep.get("confidence")
            try:
                c = float(conf)
            except Exception:
                c = None
            if c is not None:
                if c < 40:
                    conf_bins["0-39"].append(ret)
                elif c < 60:
                    conf_bins["40-59"].append(ret)
                elif c < 80:
                    conf_bins["60-79"].append(ret)
                else:
                    conf_bins["80-100"].append(ret)

        # Finalize
        out = {
            "ok": True,
            "rows": int(len(df)),
            "filters": {"symbol": symbol, "timeframe": timeframe},
            "overall": {
                "win_rate": round(float((df["outcome_return_pct"] > 0).mean()) * 100.0),
                "avg_return_pct": round(float(df["outcome_return_pct"].mean()), 3),
                "median_return_pct": round(float(df["outcome_return_pct"].median()), 3),
            },
            "by_recommendation": {},
            "by_confidence": {},
        }

        for k, v in rec_counts.items():
            n = max(int(v.get("n") or 0), 1)
            out["by_recommendation"][k] = {
                "n": n,
                "win_rate": round((float(v.get("wins") or 0) / n) * 100.0),
                "avg_return_pct": round(float(v.get("avg_ret") or 0.0) / n, 3),
            }

        for b, arr in conf_bins.items():
            if not arr:
                continue
            out["by_confidence"][b] = {
                "n": len(arr),
                "avg_return_pct": round(sum(arr) / max(len(arr), 1), 3),
                "win_rate": round(sum(1 for x in arr if x > 0) / max(len(arr), 1) * 100.0),
            }

        return out
    except Exception as e:
        return {"ok": False, "reason": str(e)}

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
