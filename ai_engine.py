# ai_engine.py
import pandas as pd

from ai_engine_core.core import _normalize_symbol, _map_period_from_timeframe
from ai_engine_core.ohlcv import _ensure_ohlcv_columns
from ai_engine_core.indicators import _compute_indicators
from ai_engine_core.technicals import analyze_technicals
from ai_engine_core.vsa import analyze_vsa
from ai_engine_core.risk import _risk_plan_from_atr_sr
from ai_engine_core.reporting import build_report


def _fetch_ohlcv(symbol: str, timeframe: str = "1d") -> pd.DataFrame:
    """
    يحاول:
    1) market_data.get_chart_history / fetch_chart_history / get_history
    2) yfinance fallback
    """
    sym = _normalize_symbol(symbol)
    period = _map_period_from_timeframe(timeframe)

    # 1) Project data source
    try:
        import market_data

        for fn_name in ["get_chart_history", "fetch_chart_history", "get_history", "fetch_history"]:
            if hasattr(market_data, fn_name):
                fn = getattr(market_data, fn_name)
                try:
                    df = fn(sym, period=period, interval=timeframe)  # بعض الدوال تدعم period/interval
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        return df
                except TypeError:
                    # جرب بدون interval
                    try:
                        df = fn(sym, period=period)
                        if isinstance(df, pd.DataFrame) and not df.empty:
                            return df
                    except Exception:
                        pass
                except Exception:
                    pass
    except Exception:
        pass

    # 2) yfinance fallback
    try:
        import yfinance as yf

        df = yf.download(sym, period=period, interval=timeframe, auto_adjust=False, progress=False)
        if isinstance(df, pd.DataFrame) and not df.empty:
            return df
    except Exception:
        pass

    return pd.DataFrame()


def generate_ai_report(symbol: str, timeframe: str = "1d", fin: dict = None):
    """
    fin: (اختياري) مخرجات calculate_portfolio_metrics لو تبي ربط المحفظة لاحقاً.
    """
    try:
        sym = _normalize_symbol(symbol)

        raw = _fetch_ohlcv(sym, timeframe=timeframe)
        if raw is None or raw.empty:
            return {"__error__": True, "message": "لا توجد بيانات سعرية كافية."}

        df = _ensure_ohlcv_columns(raw)

        ind = _compute_indicators(df) or {}

        tech_pack = analyze_technicals(df, ind)
        vsa_pack = analyze_vsa(df, lookback=80)

        # risk plan
        direction = tech_pack.get("direction_hint") or "neutral"
        risk_plan = _risk_plan_from_atr_sr(df, ind, direction=direction)

        # portfolio pack (اختياري: إذا مررت fin)
        portfolio_pack = {"gates": {"pass": True, "reasons": [], "warnings": []}, "notes": []}
        try:
            if fin and isinstance(fin, dict) and "all_trades" in fin:
                from ai_engine_core.portfolio_risk import compute_cash_percent, portfolio_gates

                cash_pct = compute_cash_percent(fin)
                g = portfolio_gates(fin.get("all_trades"), sym, cash_pct=cash_pct)
                portfolio_pack["gates"] = g
                portfolio_pack["notes"] = [f"Cash% ≈ {cash_pct:.2f}%"]
        except Exception:
            pass

        rep = build_report(
            symbol=sym,
            timeframe=timeframe,
            df=df,
            tech_pack=tech_pack,
            vsa_pack=vsa_pack,
            fund_pack=None,          # جاهز نربطه لاحقاً
            risk_plan=risk_plan,
            portfolio_pack=portfolio_pack,
        )

        # (اختياري) logging
        try:
            from ai_engine_core.logging_learning import log_ai_signal

            log_ai_signal(
                symbol=sym,
                timeframe=timeframe,
                features=rep.get("features") or {},
                report=rep,
                horizon_days=20,
                sector=None,
                strategy_name="osoli_ai_v1",
            )
        except Exception:
            pass

        return rep

    except Exception as e:
        return {"__error__": True, "__trace__": str(e)}
