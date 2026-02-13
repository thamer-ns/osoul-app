# ai_engine_core/logging_learning.py

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .db import _safe_import_db, _try_exec, _ensure_ai_tables
from .core import _now_str

def _json_dumps(obj) -> str:
    try:
        return json.dumps(obj or {}, ensure_ascii=False)
    except Exception:
        return "{}"

def log_ai_signal(
    symbol,
    timeframe,
    features: dict,
    report: dict,
    horizon_days: int = 20,
    sector: str = None,
    strategy_name: str = None,
    market_trend: str = None,
    regime: str = None,
    ctx_key: str = None,
    horizons: List[int] = None,
):
    """Log a model decision (signal) for later outcome evaluation & learning."""
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return None

    _ensure_ai_tables()

    signal_id = str(uuid.uuid4())
    horizons = horizons or [5, 10, 20, 60]

    # Try new schema first (context columns). Fallback to old insert if DB isn't migrated yet.
    try:
        ok = _try_exec(
            """
            INSERT INTO ai_signals
            (id, created_at, symbol, sector, timeframe, horizon_days, strategy_name, market_trend, regime, ctx_key, horizons_json, features_json, report_json)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                signal_id,
                _now_str(),
                str(symbol),
                (str(sector) if sector is not None else None),
                str(timeframe),
                int(horizon_days),
                (str(strategy_name) if strategy_name is not None else None),
                (str(market_trend) if market_trend is not None else None),
                (str(regime) if regime is not None else None),
                (str(ctx_key) if ctx_key is not None else None),
                _json_dumps(horizons),
                _json_dumps(features),
                _json_dumps(report),
            ),
        )
        if ok:
            return signal_id
    except Exception:
        pass

    try:
        ok = _try_exec(
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
                _json_dumps(features),
                _json_dumps(report),
            ),
        )
        return signal_id if ok else None
    except Exception:
        return None

def _get_weight(key: str, default=1.0) -> float:
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

def _set_weight(key: str, weight: float) -> bool:
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

def get_effective_weight(feature_key: str, ctx_key: str = None, default: float = 1.0) -> float:
    """Context-aware weight: global weight * context-specific weight (bounded by DB stored values)."""
    w = _get_weight(str(feature_key), default)
    if ctx_key:
        w_ctx = _get_weight(f"ctx:{ctx_key}|feat:{feature_key}", 1.0)
        w = float(w) * float(w_ctx)
    # safety clamp
    return float(max(0.1, min(3.0, w)))

# ============================================================
# ✅ Outcomes: multi-horizon + risk (TP/SL)
# ============================================================

def _parse_dt(x) -> Optional[pd.Timestamp]:
    try:
        if x is None or str(x).strip() == "":
            return None
        return pd.to_datetime(x)
    except Exception:
        return None

def _trade_outcome_from_path(
    df_path: pd.DataFrame,
    entry: float,
    stop: float,
    tp: float,
    direction: str = "buy",
) -> Tuple[float, int, int, str, float, float, float]:
    """Evaluate TP/SL path (first-hit logic). Returns (ret%, hit_tp, hit_sl, reason, exit_price, max_dd%, max_ru%)."""
    if df_path is None or df_path.empty:
        return 0.0, 0, 0, "no_path", float(entry), 0.0, 0.0

    direction = (direction or "buy").lower().strip()
    is_sell = direction == "sell"

    highs = pd.to_numeric(df_path.get("High"), errors="coerce")
    lows  = pd.to_numeric(df_path.get("Low"), errors="coerce")
    closes = pd.to_numeric(df_path.get("Close"), errors="coerce")

    # Max drawdown/runup vs entry
    try:
        if is_sell:
            # for sell: adverse move is high above entry
            max_dd = ((highs.max() - entry) / entry) * 100.0 if entry else 0.0
            max_ru = ((entry - lows.min()) / entry) * 100.0 if entry else 0.0
        else:
            max_dd = ((entry - lows.min()) / entry) * 100.0 if entry else 0.0
            max_ru = ((highs.max() - entry) / entry) * 100.0 if entry else 0.0
    except Exception:
        max_dd, max_ru = 0.0, 0.0

    hit_tp = hit_sl = 0
    exit_price = float(closes.iloc[-1]) if len(closes) else float(entry)
    reason = "close"

    # First-hit logic
    for i in range(len(df_path)):
        h = float(highs.iloc[i]) if pd.notna(highs.iloc[i]) else None
        l = float(lows.iloc[i]) if pd.notna(lows.iloc[i]) else None
        if h is None or l is None:
            continue

        if is_sell:
            # TP is lower, SL is higher
            if stop is not None and h >= float(stop):
                hit_sl = 1
                exit_price = float(stop)
                reason = "sl"
                break
            if tp is not None and l <= float(tp):
                hit_tp = 1
                exit_price = float(tp)
                reason = "tp"
                break
        else:
            if stop is not None and l <= float(stop):
                hit_sl = 1
                exit_price = float(stop)
                reason = "sl"
                break
            if tp is not None and h >= float(tp):
                hit_tp = 1
                exit_price = float(tp)
                reason = "tp"
                break

    if entry and entry > 0:
        if is_sell:
            ret = ((entry - exit_price) / entry) * 100.0
        else:
            ret = ((exit_price - entry) / entry) * 100.0
    else:
        ret = 0.0

    return float(ret), int(hit_tp), int(hit_sl), str(reason), float(exit_price), float(max_dd), float(max_ru)

def _insert_outcome(signal_id: str, horizon_days: int, payload: dict) -> bool:
    execute_query, _ = _safe_import_db()
    if not execute_query:
        return False
    _ensure_ai_tables()

    oid = str(uuid.uuid4())
    try:
        return bool(
            _try_exec(
                """
                INSERT INTO ai_outcomes
                (id, signal_id, horizon_days, return_pct, win, exit_reason, hit_tp, hit_sl, max_dd_pct, max_ru_pct, exit_price, exit_at, context_json)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    oid,
                    str(signal_id),
                    int(horizon_days),
                    float(payload.get("return_pct", 0.0)),
                    int(payload.get("win", 0)),
                    str(payload.get("exit_reason") or "close"),
                    int(payload.get("hit_tp", 0)),
                    int(payload.get("hit_sl", 0)),
                    float(payload.get("max_dd_pct", 0.0)),
                    float(payload.get("max_ru_pct", 0.0)),
                    float(payload.get("exit_price", 0.0)),
                    str(payload.get("exit_at") or _now_str()),
                    _json_dumps(payload.get("context") or {}),
                ),
            )
        )
    except Exception:
        return False

def evaluate_pending_outcomes_pro(
    horizons: List[int] = None,
    max_rows: int = 400,
    interval: str = "1d",
) -> Dict[str, Any]:
    """Evaluate outcomes for signals that don't yet have outcomes for given horizons."""
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()

    horizons = horizons or [5, 10, 20, 60]
    try:
        signals = fetch_table("ai_signals")
        if signals is None or signals.empty:
            return {"ok": True, "evaluated": 0, "reason": "no_signals"}

        outcomes = fetch_table("ai_outcomes")
        if outcomes is None:
            outcomes = pd.DataFrame()

        # resolve missing outcomes by (signal_id, horizon)
        existing = set()
        try:
            if not outcomes.empty:
                for _, r in outcomes.iterrows():
                    existing.add((str(r.get("signal_id")), int(r.get("horizon_days") or 0)))
        except Exception:
            existing = set()

        # Sort by created_at asc (older first)
        if "created_at" in signals.columns:
            signals = signals.sort_values("created_at", ascending=True)

        signals = signals.tail(int(max_rows))

        from market_data import get_chart_history  # cached
        evaluated = 0

        for _, s in signals.iterrows():
            sid = str(s.get("id") or "")
            sym = str(s.get("symbol") or "")
            if not sid or not sym:
                continue

            created_at = _parse_dt(s.get("created_at"))
            if created_at is None:
                continue

            # Pull report/risk plan
            try:
                report = json.loads(s.get("report_json") or "{}")
            except Exception:
                report = {}

            risk_plan = report.get("risk_plan") or {}
            direction = str(risk_plan.get("direction") or "buy")
            entry = risk_plan.get("entry")
            stop = risk_plan.get("stop")
            tp = risk_plan.get("target1")

            # Need entry; fallback to last known close at signal creation
            df_hist = get_chart_history(sym, period=None, interval=str(interval), years=5)
            if df_hist is None or df_hist.empty or "Close" not in df_hist.columns:
                continue

            df_hist = df_hist.copy()
            df_hist.index = pd.to_datetime(df_hist.index)

            # Find bar index at/after created_at
            df_future = df_hist[df_hist.index >= created_at]
            if df_future.empty:
                continue

            if entry is None:
                try:
                    entry = float(pd.to_numeric(df_future["Close"].iloc[0], errors="coerce") or 0.0)
                except Exception:
                    entry = 0.0

            if not entry or float(entry) <= 0:
                continue

            # Context
            ctx = {
                "market_trend": s.get("market_trend"),
                "regime": s.get("regime"),
                "ctx_key": s.get("ctx_key"),
                "sector": s.get("sector"),
                "timeframe": s.get("timeframe"),
            }

            for h in horizons:
                if (sid, int(h)) in existing:
                    continue

                # Need at least h+1 bars
                df_path = df_future.head(int(h) + 1)
                if len(df_path) < int(h) + 1:
                    continue

                ret, hit_tp, hit_sl, reason, exit_price, max_dd, max_ru = _trade_outcome_from_path(
                    df_path,
                    entry=float(entry),
                    stop=(float(stop) if stop is not None else None),
                    tp=(float(tp) if tp is not None else None),
                    direction=direction,
                )
                win = 1 if float(ret) > 0 else 0

                payload = {
                    "return_pct": float(ret),
                    "win": int(win),
                    "exit_reason": reason,
                    "hit_tp": int(hit_tp),
                    "hit_sl": int(hit_sl),
                    "max_dd_pct": float(max_dd),
                    "max_ru_pct": float(max_ru),
                    "exit_price": float(exit_price),
                    "exit_at": str(df_path.index[-1]),
                    "context": ctx,
                }

                if _insert_outcome(sid, int(h), payload):
                    evaluated += 1
                    existing.add((sid, int(h)))

        return {"ok": True, "evaluated": evaluated, "horizons": horizons}
    except Exception as e:
        return {"ok": False, "reason": str(e)}

# ============================================================
# ✅ Learning: context-aware + safety rails
# ============================================================

def learn_from_history_pro(
    target_horizon: int = 20,
    min_samples: int = 40,
    max_rows: int = 1200,
    max_step: float = 0.04,
    w_min: float = 0.4,
    w_max: float = 2.2,
    stability_window: int = 2,
) -> Dict[str, Any]:
    """Update weights using outcomes, conditioned on context (market/regime/sector) with safety rails."""
    execute_query, fetch_table = _safe_import_db()
    if not execute_query or not fetch_table:
        return {"ok": False, "reason": "DB not available"}

    _ensure_ai_tables()

    try:
        sig = fetch_table("ai_signals")
        out = fetch_table("ai_outcomes")
        if sig is None or sig.empty or out is None or out.empty:
            return {"ok": True, "updated": 0, "reason": "no_data"}

        # filter target horizon
        out = out[pd.to_numeric(out.get("horizon_days"), errors="coerce") == int(target_horizon)]
        if out.empty:
            return {"ok": True, "updated": 0, "reason": "no_target_horizon"}

        # Join
        sig = sig[["id", "created_at", "sector", "timeframe", "features_json", "market_trend", "regime", "ctx_key"]].copy()
        sig["id"] = sig["id"].astype(str)
        out["signal_id"] = out["signal_id"].astype(str)

        df = out.merge(sig, left_on="signal_id", right_on="id", how="left", suffixes=("", "_s"))
        if df.empty:
            return {"ok": True, "updated": 0, "reason": "no_join"}

        # sort by created_at for stability windows
        if "created_at" in df.columns:
            df["created_at"] = pd.to_datetime(df["created_at"], errors="coerce")
            df = df.sort_values("created_at", ascending=True)

        df = df.tail(int(max_rows))

        # Accumulate stats per (ctx_key, feature)
        stats: Dict[str, Dict[str, Any]] = {}
        for _, r in df.iterrows():
            try:
                feats = json.loads(r.get("features_json") or "{}")
            except Exception:
                feats = {}
            win = int(r.get("win") or 0)

            ctx = str(r.get("ctx_key") or "").strip() or "global"
            # Use sector/regime/market as fallback if ctx_key missing
            if ctx == "global":
                mt = str(r.get("market_trend") or "UNK")
                rg = str(r.get("regime") or "UNK")
                sec = str(r.get("sector") or "UNK")
                ctx = f"mkt={mt}|reg={rg}|sec={sec}"

            for k, v in (feats or {}).items():
                # Only learn on boolean 0/1 features; skip internal/meta keys
                if str(k).startswith("__"):
                    continue
                if isinstance(v, (bool, int)) and int(v) in (0, 1):
                    if int(v) != 1:
                        continue
                    key = f"{ctx}|{k}"
                    s = stats.setdefault(key, {"wins": 0, "n": 0, "series": []})
                    s["wins"] += win
                    s["n"] += 1
                    s["series"].append(win)

        updated = 0
        skipped = 0

        for key, s in stats.items():
            n = int(s["n"])
            if n < int(min_samples):
                skipped += 1
                continue

            series = list(s.get("series") or [])
            # Stability: require last window(s) not contradict previous
            if stability_window and len(series) >= 2 * min_samples:
                last = series[-min_samples:]
                prev = series[-2*min_samples:-min_samples]
                wr_last = sum(last) / len(last) if last else 0.0
                wr_prev = sum(prev) / len(prev) if prev else 0.0
                # if performance collapses, don't update
                if wr_last + 0.01 < wr_prev:
                    skipped += 1
                    continue

            win_rate = float(s["wins"]) / float(n) if n else 0.0

            # Derive feature and ctx
            try:
                ctx, feat = key.rsplit("|", 1)
            except Exception:
                ctx, feat = "global", key

            # Convert to weight key
            w_key = f"ctx:{ctx}|feat:{feat}"
            w = _get_weight(w_key, 1.0)

            # Update rule (bounded)
            if win_rate >= 0.58:
                w = min(w + float(max_step), float(w_max))
            elif win_rate <= 0.42:
                w = max(w - float(max_step), float(w_min))
            else:
                continue

            if _set_weight(w_key, float(w)):
                updated += 1

        return {"ok": True, "updated": updated, "skipped": skipped, "learned": len(stats), "horizon": int(target_horizon)}
    except Exception as e:
        return {"ok": False, "reason": str(e)}


# ============================================================
# Backwards-compatible API
# ============================================================
def update_ai_outcome(signal_id: str, outcome: dict | None = None, **kwargs) -> bool:
    """تحديث نتيجة توصية/إشارة (Backwards compatibility).

    بعض الصفحات/الموديولات القديمة تتوقع وجود update_ai_outcome.
    هذه الدالة تجمع المدخلات ثم تسجّل outcome داخل SQLite إن توفر.
    """
    try:
        payload = {}
        if isinstance(outcome, dict):
            payload.update(outcome)
        payload.update(kwargs or {})
        payload.setdefault("signal_id", signal_id)

        # نستخدم نفس جدول outcomes عبر _insert_outcome
        _insert_outcome(payload)
        return True
    except Exception:
        # لا نكسر التطبيق إذا لم تتوفر قاعدة البيانات أو كانت البيئة Read-only
        return False

