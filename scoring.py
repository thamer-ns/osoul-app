# ai_engine_core/scoring.py
from typing import Dict, Any


def clamp(x, lo, hi):
    try:
        return max(min(float(x), float(hi)), float(lo))
    except Exception:
        return lo


def merge_features(*dicts):
    out = {}
    for d in dicts:
        if not isinstance(d, dict):
            continue
        for k, v in d.items():
            out[k] = v
    return out


def osoli_score(module_scores: Dict[str, float], module_weights: Dict[str, float] = None):
    """
    module_scores: {tech, vsa, fund, structure, risk}
    returns total in [-100..+100] (تقريبي)
    """
    w = module_weights or {
        "tech": 1.0,
        "vsa": 0.9,
        "fund": 1.0,
        "structure": 0.8,
        "risk": 0.6,
    }

    s = 0.0
    for k, v in (module_scores or {}).items():
        ww = float(w.get(k, 1.0))
        s += float(v or 0.0) * ww

    # كل Module عندنا عادة -6..+6
    # تحويل تقريبي إلى 100
    total = clamp(s * 10.5, -100, 100)
    return total


def recommendation_from_score(total: float, direction_hint: str = "neutral"):
    """
    Recommendation mapping
    """
    total = float(total or 0.0)
    dh = (direction_hint or "neutral").lower().strip()

    if total >= 65:
        return "شراء قوي" if dh != "sell" else "تعارض قوي (فني/إشارة بيع)"
    if total >= 40:
        return "شراء" if dh != "sell" else "حياد (تعارض)"
    if total >= 15:
        return "حياد إيجابي"
    if total <= -65:
        return "بيع قوي" if dh != "buy" else "تعارض قوي (فني/إشارة شراء)"
    if total <= -40:
        return "بيع" if dh != "buy" else "حياد (تعارض)"
    if total <= -15:
        return "حياد سلبي"
    return "حياد"


def build_evidence(tech: dict, vsa: dict, fund: dict = None, extra_notes=None):
    positives = []
    negatives = []
    notes = []

    def add_reasons(pack: dict):
        if not isinstance(pack, dict):
            return
        for r in (pack.get("reasons") or []):
            rr = str(r).strip()
            if not rr:
                continue
            # تصنيف بسيط
            if any(k in rr for k in ["🔴", "🛑", "هبوط", "تصريف", "ضعف", "كسر", "Upthrust", "No Demand"]):
                negatives.append(rr)
            else:
                positives.append(rr)

    add_reasons(tech)
    add_reasons(vsa)
    add_reasons(fund or {})

    for n in (extra_notes or []):
        s = str(n).strip()
        if s:
            notes.append(s)

    # قص
    positives = positives[:10]
    negatives = negatives[:10]
    notes = notes[:10]

    return {
        "positives": positives,
        "negatives": negatives,
        "notes": notes,
        "top_evidence": positives[:3],
        "top_risks": negatives[:3],
    }
