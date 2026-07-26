"""Confirmed-candle advanced indicators for Osoli v2."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


def _n(x: Any, d: float = 0.0) -> float:
    try:
        return d if x is None or pd.isna(x) else float(x)
    except Exception:
        return d


def _clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, float(x)))


def _c(df: pd.DataFrame, name: str) -> pd.Series:
    for key in (name, name.lower(), name.upper(), name.capitalize()):
        if key in df.columns:
            return pd.to_numeric(df[key], errors="coerce")
    raise KeyError(f"Missing {name}")


def _bias(score: float) -> str:
    return "bullish" if score >= 20 else "bearish" if score <= -20 else "neutral"


def _result(name: str, score: float, confidence: float, summary: str, *,
            evidence=None, signals=None, features=None, warnings=None, errors=None) -> Dict[str, Any]:
    score_i = int(round(_clip(score, -100, 100)))
    return {
        "name": name,
        "bias": _bias(score_i),
        "direction_score": score_i,
        "confidence": int(round(_clip(confidence, 0, 100))),
        "summary": summary,
        "evidence": evidence or [],
        "signals": signals or [],
        "features": features or {},
        "warnings": warnings or [],
        "errors": errors or [],
    }


def _intraday_delta(tf: str) -> pd.Timedelta | None:
    aliases = {"1m": "1min", "5m": "5min", "15m": "15min", "30m": "30min",
               "60m": "60min", "1h": "1h", "2h": "2h", "4h": "4h"}
    value = aliases.get(str(tf).lower(), str(tf).lower())
    try:
        if value.endswith("min"):
            return pd.Timedelta(minutes=int(value[:-3]))
        if value.endswith("h"):
            return pd.Timedelta(hours=int(value[:-1]))
    except Exception:
        pass
    return None


def confirmed_frame(df: pd.DataFrame, timeframe: str) -> Tuple[pd.DataFrame, bool]:
    if df is None or df.empty:
        return pd.DataFrame(), False
    out = df.copy().sort_index()
    excluded = False
    try:
        idx = pd.to_datetime(out.index, errors="coerce")
        out = out.loc[~pd.isna(idx)].copy()
        out.index = idx[~pd.isna(idx)]
        now = pd.Timestamp.now(tz="Asia/Riyadh")
        last = pd.Timestamp(out.index[-1])
        last = last.tz_localize("Asia/Riyadh") if last.tzinfo is None else last.tz_convert("Asia/Riyadh")
        tf = str(timeframe or "1d").lower()
        delta = _intraday_delta(tf)
        live = False
        if delta is not None:
            live = last + delta > now
        elif tf in {"1d", "d", "day", "1day"}:
            live = last.date() == now.date() and now < now.normalize() + pd.Timedelta(hours=15, minutes=20)
        elif tf in {"1wk", "1w", "week"}:
            same_week = (last.isocalendar().year, last.isocalendar().week) == (now.isocalendar().year, now.isocalendar().week)
            live = same_week and not (now.weekday() == 3 and now.time() >= pd.Timestamp("15:20").time())
        elif tf in {"1mo", "1month", "month"}:
            live = (last.year, last.month) == (now.year, now.month)
        if live and len(out) > 1:
            out = out.iloc[:-1]
            excluded = True
    except Exception:
        if len(out) > 2:
            out = out.iloc[:-1]
            excluded = True
    return out, excluded


def _rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    return (100 - 100 / (1 + gain.div(loss.replace(0, np.nan)))).fillna(50)


def _atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    h, l, c = _c(df, "High"), _c(df, "Low"), _c(df, "Close")
    pc = c.shift()
    tr = pd.concat([(h-l).abs(), (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()


def _pivots(s: pd.Series, left=3, right=3) -> Tuple[np.ndarray, np.ndarray]:
    v = pd.to_numeric(s, errors="coerce").to_numpy(float)
    hi, lo = np.zeros(len(v), bool), np.zeros(len(v), bool)
    for i in range(left, len(v)-right):
        w = v[i-left:i+right+1]
        if np.isfinite(w).all():
            hi[i] = v[i] == w.max() and (w == v[i]).sum() == 1
            lo[i] = v[i] == w.min() and (w == v[i]).sum() == 1
    return hi, lo


def rls_forecast(df: pd.DataFrame) -> Dict[str, Any]:
    if len(df) < 40:
        return _result("RLS Forecast", 0, 10, "بيانات غير كافية.", warnings=["يلزم 40 شمعة مغلقة."])
    close = _c(df, "Close").dropna()
    x = np.arange(len(close), dtype=float)
    y = np.log(close.to_numpy(float))
    weights = 0.985 ** (len(close)-1-x)
    X = np.column_stack([np.ones(len(x)), x])
    try:
        beta = np.linalg.solve(X.T @ (weights[:, None] * X), X.T @ (weights*y))
    except np.linalg.LinAlgError:
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
    fitted = X @ beta
    rmse = float(np.sqrt(np.average((y-fitted)**2, weights=weights)))
    mean = float(np.exp(fitted[-1]))
    last = float(close.iloc[-1])
    slope_pct = float((np.exp(beta[1])-1)*100)
    deviation = last/mean-1 if mean > 0 else 0
    score = _clip(slope_pct*250 - deviation*300, -100, 100)
    band = 1.7*rmse
    upper, lower = float(np.exp(fitted[-1]+band)), float(np.exp(fitted[-1]-band))
    signals = []
    if len(close) >= 2 and close.iloc[-2] < lower <= last:
        signals.append({"type":"BUY","kind":"MEAN_REVERSION_CONFIRMED","price":last,"confirmation":"closed_candle","reason":"عاد الإغلاق داخل النطاق من الأسفل."})
    if len(close) >= 2 and close.iloc[-2] > upper >= last:
        signals.append({"type":"SELL","kind":"MEAN_REVERSION_CONFIRMED","price":last,"confirmation":"closed_candle","reason":"عاد الإغلاق داخل النطاق من الأعلى."})
    summary = "اتجاه تكيفي صاعد." if score >= 20 else "اتجاه تكيفي هابط." if score <= -20 else "اتجاه تكيفي محايد."
    return _result("RLS Forecast", score, 55+min(15,len(df)/15)-min(25,rmse*500), summary,
                   evidence=[f"الميل لكل شمعة {slope_pct:.3f}%", f"الانحراف عن المتوسط {deviation*100:.2f}%"],
                   signals=signals, features={"close":last,"mean":mean,"upper":upper,"lower":lower,"slope_pct_per_bar":slope_pct,"rmse":rmse})


def chaos_weighted_rsi(df: pd.DataFrame) -> Dict[str, Any]:
    if len(df) < 50:
        return _result("Chaos Weighted RSI", 0, 10, "بيانات غير كافية.", warnings=["يلزم 50 شمعة مغلقة."])
    close = _c(df, "Close").dropna()
    raw = _rsi(close)
    vol = close.pct_change().rolling(30).std()
    low, high = vol.rolling(120,min_periods=30).quantile(.1), vol.rolling(120,min_periods=30).quantile(.9)
    chaos = ((vol-low)/(high-low).replace(0,np.nan)).clip(0,1).fillna(.5)
    spans = (3+chaos*8).round().astype(int)
    vals=[]; prev=50.0
    for r, span in zip(raw, spans):
        alpha=2/(int(span)+1); prev=alpha*float(r)+(1-alpha)*prev; vals.append(prev)
    wrsi=pd.Series(vals,index=raw.index)
    last, previous=float(wrsi.iloc[-1]),float(wrsi.iloc[-2])
    score=_clip((last-50)*2,-70,70); signals=[]
    if previous <= 30 < last:
        signals.append({"type":"BUY","kind":"OVERSOLD_EXIT_CONFIRMED","value":last,"confirmation":"closed_candle","reason":"خروج مؤكد من التشبع البيعي."})
    if previous >= 70 > last:
        signals.append({"type":"SELL","kind":"OVERBOUGHT_EXIT_CONFIRMED","value":last,"confirmation":"closed_candle","reason":"خروج مؤكد من التشبع الشرائي."})
    ph,pl=_pivots(close); lows=np.where(pl)[0]; highs=np.where(ph)[0]
    if len(lows)>=2:
        a,b=lows[-2],lows[-1]
        if close.iloc[b]<close.iloc[a] and wrsi.iloc[b]>wrsi.iloc[a]:
            score+=20; signals.append({"type":"BUY","kind":"BULLISH_DIVERGENCE","confirmation":"closed_candle","reason":"دايفرجنس إيجابي بين قاعين مؤكدين."})
    if len(highs)>=2:
        a,b=highs[-2],highs[-1]
        if close.iloc[b]>close.iloc[a] and wrsi.iloc[b]<wrsi.iloc[a]:
            score-=20; signals.append({"type":"SELL","kind":"BEARISH_DIVERGENCE","confirmation":"closed_candle","reason":"دايفرجنس سلبي بين قمتين مؤكدتين."})
    summary="الزخم إيجابي." if score>=20 else "الزخم سلبي." if score<=-20 else "الزخم متوازن."
    return _result("Chaos Weighted RSI",score,55+(1-float(chaos.iloc[-1]))*15,summary,
                   evidence=[f"WRSI {last:.2f}",f"الاضطراب {float(chaos.iloc[-1]):.2f}"],signals=signals,
                   features={"wrsi":last,"raw_rsi":float(raw.iloc[-1]),"chaos":float(chaos.iloc[-1]),"adaptive_span":int(spans.iloc[-1])})


def volume_profile_clusters(df: pd.DataFrame, buckets: int = 16) -> Dict[str, Any]:
    if len(df) < 60:
        return _result("Volume Profile Clusters",0,10,"بيانات غير كافية.",warnings=["يلزم 60 شمعة مغلقة."])
    h,l,c,v=_c(df,"High"),_c(df,"Low"),_c(df,"Close"),_c(df,"Volume").fillna(0)
    edges=np.linspace(float(l.min()),float(h.max()),max(6,buckets)+1)
    vols=np.zeros(len(edges)-1)
    for hi,lo,vol in zip(h,l,v):
        touched=np.where((edges[:-1]<=hi)&(edges[1:]>=lo))[0]
        if len(touched) and np.isfinite(vol) and vol>0:
            vols[touched]+=float(vol)/len(touched)
    total=float(vols.sum())
    if total<=0:
        return _result("Volume Profile Clusters",0,20,"الحجم غير متاح.",warnings=["بيانات الحجم صفرية."])
    centers=(edges[:-1]+edges[1:])/2
    top=np.argsort(vols)[::-1][:3]; pocs=[float(centers[i]) for i in top]
    last=float(c.iloc[-1]); distance=last/pocs[0]-1 if pocs[0]>0 else 0
    score=_clip(distance*250,-45,45)
    rows=[{"price_low":float(edges[i]),"price_high":float(edges[i+1]),"poc":float(centers[i]),"volume":float(vols[i]),"volume_share":float(vols[i]/total)} for i in range(len(vols))]
    signals=[{"type":"INFO","kind":"NEAR_MAIN_POC","poc":pocs[0],"reason":"السعر قريب من أكبر منطقة حجم."}] if abs(distance)<=.01 else []
    summary="أعلى منطقة الحجم الرئيسة." if score>=20 else "أسفل منطقة الحجم الرئيسة." if score<=-20 else "قريب من منطقة الحجم الرئيسة."
    return _result("Volume Profile Clusters",score,60,summary,evidence=["المناطق الأقوى: "+"، ".join(f"{x:.2f}" for x in pocs)],
                   signals=signals,features={"main_poc":pocs[0],"distance_from_poc_pct":distance*100,"clusters":rows})


def trendline_breakout(df: pd.DataFrame, lookback: int = 140) -> Dict[str, Any]:
    if len(df) < 70:
        return _result("Trendline Breakout",0,10,"بيانات غير كافية.",warnings=["يلزم 70 شمعة مغلقة."])
    w=df.tail(lookback); c=_c(w,"Close").reset_index(drop=True); h=_c(w,"High").reset_index(drop=True); l=_c(w,"Low").reset_index(drop=True)
    v=_c(w,"Volume").fillna(0).reset_index(drop=True); atr=_atr(w).reset_index(drop=True)
    ph,pl=_pivots(c); highs=np.where(ph)[0]; lows=np.where(pl)[0]
    features={}; evidence=[]; signals=[]; score=0.0; i=len(c)-1; p=i-1; atr_last=_n(atr.iloc[-1])
    volume_ok=float(v.iloc[-1]) >= _n(v.rolling(20).mean().iloc[-1],float(v.iloc[-1]))
    if len(highs)>=2:
        a,b=int(highs[-2]),int(highs[-1]); m=(float(h.iloc[b])-float(h.iloc[a]))/max(1,b-a); q=float(h.iloc[b])-m*b
        now,prev=m*i+q,m*p+q; features["resistance_trendline"]=now; evidence.append(f"ميل المقاومة {m:.4f}")
        margin=float(c.iloc[-1])-now
        if c.iloc[-1]>now and c.iloc[-2]<=prev and (atr_last<=0 or margin>=.15*atr_last):
            score+=75 if volume_ok else 65
            signals.append({"type":"BUY","kind":"BREAKOUT_RESISTANCE_CONFIRMED","price":float(c.iloc[-1]),"trigger":float(now),"confirmation":"closed_candle","reason":"إغلاق مؤكد أعلى المقاومة مع هامش ATR."})
    if len(lows)>=2:
        a,b=int(lows[-2]),int(lows[-1]); m=(float(l.iloc[b])-float(l.iloc[a]))/max(1,b-a); q=float(l.iloc[b])-m*b
        now,prev=m*i+q,m*p+q; features["support_trendline"]=now; evidence.append(f"ميل الدعم {m:.4f}")
        margin=now-float(c.iloc[-1])
        if c.iloc[-1]<now and c.iloc[-2]>=prev and (atr_last<=0 or margin>=.15*atr_last):
            score-=75 if volume_ok else 65
            signals.append({"type":"SELL","kind":"BREAKDOWN_SUPPORT_CONFIRMED","price":float(c.iloc[-1]),"trigger":float(now),"confirmation":"closed_candle","reason":"إغلاق مؤكد أسفل الدعم مع هامش ATR."})
    summary="اختراق صاعد مؤكد." if score>=20 else "كسر هابط مؤكد." if score<=-20 else "لا يوجد اختراق أو كسر مؤكد."
    features.update({"atr14":atr_last,"volume":float(v.iloc[-1]),"volume_ma20":_n(v.rolling(20).mean().iloc[-1]),"confirmation":"closed_candle"})
    return _result("Trendline Breakout",score,65 if features else 25,summary,evidence=evidence,signals=signals,features=features)


def compute_advanced_technical_pack(df: pd.DataFrame, symbol: str = "", timeframe: str = "1d") -> Dict[str, Any]:
    confirmed, excluded=confirmed_frame(df,timeframe)
    meta={"symbol":str(symbol),"timeframe":str(timeframe),"input_rows":len(df) if df is not None else 0,
          "confirmed_rows":len(confirmed),"live_bar_excluded":excluded,"confirmation_rule":"closed_candle"}
    if confirmed.empty:
        return {"meta":meta,"bias":"neutral","direction_score":0,"confidence":0,"summary":"لا توجد شموع مغلقة صالحة.",
                "features":{},"evidence":[],"signals":[],"warnings":["لا توجد بيانات مؤكدة."],"errors":[]}
    results={"rls_forecast":rls_forecast(confirmed),"chaos_wrsi":chaos_weighted_rsi(confirmed),
             "volume_profile_clusters":volume_profile_clusters(confirmed),"trendline_breakout":trendline_breakout(confirmed)}
    vals=list(results.values()); weights=[max(.05,_n(x.get("confidence"))/100) for x in vals]
    direction=float(np.average([_n(x.get("direction_score")) for x in vals],weights=weights))
    dispersion=float(np.std([_n(x.get("direction_score")) for x in vals]))
    confidence=_clip(float(np.average([_n(x.get("confidence")) for x in vals],weights=weights))-min(25,dispersion/3),0,100)
    signals=[]; evidence=[]; warnings=[]; errors=[]; features={}
    for key,res in results.items():
        signals.extend(res.get("signals") or []); evidence.extend(f"{res.get('name',key)}: {e}" for e in (res.get("evidence") or []))
        warnings.extend(res.get("warnings") or []); errors.extend(res.get("errors") or [])
        for fk,fv in (res.get("features") or {}).items():
            if isinstance(fv,(str,int,float,bool)) or fv is None: features[f"{key}.{fk}"]=fv
    bias=_bias(direction); label={"bullish":"إيجابي","bearish":"سلبي","neutral":"محايد/مختلط"}[bias]
    return {"meta":meta,**results,"bias":bias,"direction_score":int(round(direction)),"confidence":int(round(confidence)),
            "summary":f"الميل الفني المتقدم {label} اعتمادًا على الشموع المغلقة فقط.","features":features,
            "evidence":evidence[:30],"signals":signals[:30],"warnings":list(dict.fromkeys(warnings)),"errors":list(dict.fromkeys(errors))}
