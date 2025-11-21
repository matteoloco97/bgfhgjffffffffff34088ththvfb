#!/usr/bin/env python3
# core/web_validator.py — Multi-source validator (odds/scores/dates) con consenso pesato
# Patch 2025-11:
# - Consenso pesato per dominio (fonti "affidabili" incidono di più)
# - Estrazione quote: decimali, frazionali (5/2 → 3.5) e americane (+150 → 2.5)
# - Tolleranza quote ±0.03 (post-normalizzazione a 2 decimali)
# - Date: normalizzazione estesa (yyyy-mm-dd, dd/mm/yyyy, dd-mm-yyyy, "12 nov 2025"/"12 november 2025")
# - Conflitti dettagliati per tipo, con differenza calcolata per odds
# - Output retro-compatibile con {validated, confidence, claims, conflicts}

from __future__ import annotations
import re
from typing import List, Dict, Any, Tuple
from urllib.parse import urlparse

# ---------- Regex base ----------
# punteggi: 2-1, 2:1, 2–1, 2.1 (usiamo . come separatore raro ma supportato)
_SCORE = re.compile(r"\b(\d+)\s*[-–:\.]\s*(\d+)\b")

# quote decimali (1.35, 2, 10.50). Evita match su anni concatenati.
_ODDS_DEC = re.compile(r"(?<!\d)([1-9]\d*(?:\.\d+)?|\d?\.\d+)(?!\d)")

# quote frazionali UK (5/2, 11/10) – attenzione a non ingerire date dd/mm/yyyy:
_ODDS_FRAC = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")

# quote americane (+150, -120)
_ODDS_US = re.compile(r"(?<!\d)([+-]\d{3,4})(?!\d)")

# date ISO e comuni: yyyy-mm-dd, dd/mm/yyyy, dd-mm-yyyy
_DATE_ISO = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_DATE_SL  = re.compile(r"\b(\d{1,2})[/-](\d{1,2})[/-](\d{2,4})\b")

# date con mese testuale (it/en): 12 nov 2025, 12 november 2025
_MONTH_TXT = {
    # italiano
    "gen":1,"gennaio":1, "feb":2,"febbraio":2, "mar":3,"marzo":3, "apr":4,"aprile":4,
    "mag":5,"maggio":5, "giu":6,"giugno":6, "lug":7,"luglio":7, "ago":8,"agosto":8,
    "set":9,"sett":9,"settembre":9, "ott":10,"ottobre":10, "nov":11,"novembre":11, "dic":12,"dicembre":12,
    # english
    "jan":1,"january":1, "february":2,"feb":2, "mar":3,"march":3, "apr":4,"april":4,
    "may":5, "jun":6,"june":6, "jul":7,"july":7, "aug":8,"august":8,
    "sep":9,"sept":9,"september":9, "oct":10,"october":10, "november":11,"dec":12,"december":12,
}
_DATE_TXT = re.compile(
    r"\b(\d{1,2})\s+([A-Za-zÀ-ÿ\.]{3,12})\s+(\d{2,4})\b", re.IGNORECASE
)

# ---------- Utility ----------
def _domain(u: str) -> str:
    try:
        h = urlparse(u).hostname or ""
        p = h.split(".")
        return ".".join(p[-2:]) if len(p) >= 2 else h
    except Exception:
        return ""

def _round2(x: float) -> float:
    return round(x, 2)

def _norm_score(a: str, b: str) -> str:
    return f"{int(a)}-{int(b)}"

def _norm_date_iso(y: int, m: int, d: int) -> str:
    return f"{y:04d}-{m:02d}-{d:02d}"

def _coerce_year(y: int) -> int:
    # 2 cifre → 20xx per <70, altrimenti 19xx
    if y < 100:
        return 2000 + y if y < 70 else 1900 + y
    return y

def _parse_txt_date(day: str, mon: str, year: str) -> str | None:
    try:
        d = int(day)
        m = _MONTH_TXT.get(mon.strip(".").lower())
        if not m:
            return None
        y = _coerce_year(int(year))
        return _norm_date_iso(y, m, d)
    except Exception:
        return None

def _norm_date_any(s: str) -> str:
    s = s.strip()
    m = _DATE_ISO.search(s)
    if m:
        return _norm_date_iso(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    m = _DATE_SL.search(s)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), _coerce_year(int(m.group(3)))
        return _norm_date_iso(y, mo, d)
    m = _DATE_TXT.search(s)
    if m:
        out = _parse_txt_date(m.group(1), m.group(2), m.group(3))
        if out:
            return out
    return s  # fallback: restituisce l'originale

def _dec_from_frac(num: int, den: int) -> float | None:
    if den <= 0:
        return None
    # frazionale UK N/D → decimale = 1 + N/D
    return 1.0 + (num / den)

def _dec_from_us(us: int) -> float | None:
    # +150 → 1 + 150/100 = 2.5 ; -120 → 1 + 100/120 ≈ 1.83
    try:
        if us >= 100:
            return 1.0 + (us / 100.0)
        if us <= -100:
            return 1.0 + (100.0 / abs(us))
        return None
    except Exception:
        return None

def _close_enough(a: float, b: float, tol: float = 0.03) -> bool:
    return abs(float(a) - float(b)) <= tol

# ---------- Pesi per dominio (euristica) ----------
# Nota: pesi maggiori per fonti note affidabili (solo indicativo; override possibile a runtime).
_DOMAIN_WEIGHTS: Dict[str, Dict[str, float]] = {
    # punteggi / risultati live
    "flashscore.it": {"scores": 1.35, "dates": 1.15},
    "diretta.it":    {"scores": 1.30, "dates": 1.15},
    "legaseriea.it": {"scores": 1.40, "dates": 1.25},

    # quote / odds
    "pinnacle.com":  {"odds": 1.35},
    "bet365.com":    {"odds": 1.30},
    "oddsportal.com":{"odds": 1.25},

    # default catch-all
    "*": {"odds": 1.0, "scores": 1.0, "dates": 1.0},
}

def _weight_for(domain: str, field: str) -> float:
    d = domain.lower()
    if d in _DOMAIN_WEIGHTS and field in _DOMAIN_WEIGHTS[d]:
        return float(_DOMAIN_WEIGHTS[d][field])
    base = _DOMAIN_WEIGHTS.get("*", {})
    return float(base.get(field, 1.0))

# ---------- Calcolo consenso pesato ----------
def _weighted_majorant(values: List[str], weights: List[float]) -> Tuple[float, str]:
    """
    Ritorna (ratio_pesata, valore_maggioritario).
    ratio_pesata = somma_pesi_del_valore_top / somma_pesi_totale
    """
    if not values or not weights or len(values) != len(weights):
        return 0.0, ""
    bucket: Dict[str, float] = {}
    total_w = 0.0
    for v, w in zip(values, weights):
        bucket[v] = bucket.get(v, 0.0) + float(w)
        total_w += float(w)
    if total_w <= 0.0:
        return 0.0, ""
    # top value by weight
    maj, maj_w = "", -1.0
    for k, w in bucket.items():
        if w > maj_w:
            maj, maj_w = k, w
    return (maj_w / total_w, maj)

# ---------- Classe principale ----------
class SourceValidator:
    """
    Input atteso in validate_consensus:
      extracts: [{"url":..., "title":..., "text":...}, ...]  (max ~3-5)
    Output:
      {
        "validated": bool,
        "confidence": float,
        "claims": {"majorants": {...}, "ratios": {...}},
        "conflicts": [...],
        "meta": {"field_weights": {"odds":..., "scores":..., "dates":...}}
      }
    """

    # Estrae claims dal testo
    def extract_claims(self, text: str) -> Dict[str, List[str]]:
        txt = (text or "").strip()
        claims: Dict[str, List[str]] = {"odds": [], "scores": [], "dates": []}

        # ---- Odds frazionali prima (per evitare conflitto con date) ----
        for m in _ODDS_FRAC.finditer(txt):
            try:
                n = int(m.group(1))
                d = int(m.group(2))
                # prova a escludere pattern probabile data (es. dd/mm/aaaa con den=4cifre)
                if d >= 1900 and d <= 2099:
                    continue
                dec = _dec_from_frac(n, d)
                if dec and 1.01 <= dec <= 50.0:
                    claims["odds"].append(f"{_round2(dec):.2f}")
            except Exception:
                continue

        # ---- Odds americane ----
        for m in _ODDS_US.finditer(txt):
            try:
                us = int(m.group(1))
                dec = _dec_from_us(us)
                if dec and 1.01 <= dec <= 50.0:
                    claims["odds"].append(f"{_round2(dec):.2f}")
            except Exception:
                continue

        # ---- Odds decimali ----
        for m in _ODDS_DEC.finditer(txt):
            try:
                v = float(m.group(1))
                if 1.01 <= v <= 50.0:
                    claims["odds"].append(f"{_round2(v):.2f}")
            except Exception:
                continue

        # ---- Scores ----
        for m in _SCORE.finditer(txt):
            claims["scores"].append(_norm_score(m.group(1), m.group(2)))

        # ---- Dates ----
        # prova pattern textual → iso → slash
        for m in _DATE_TXT.finditer(txt):
            nd = _parse_txt_date(m.group(1), m.group(2), m.group(3))
            if nd:
                claims["dates"].append(nd)
        for m in _DATE_ISO.finditer(txt):
            claims["dates"].append(_norm_date_iso(int(m.group(1)), int(m.group(2)), int(m.group(3))))
        for m in _DATE_SL.finditer(txt):
            d, mo, y = int(m.group(1)), int(m.group(2)), _coerce_year(int(m.group(3)))
            claims["dates"].append(_norm_date_iso(y, mo, d))

        return claims

    # Consenso "robusto": pesato per dominio, con tolleranze sulle odds
    def validate_consensus(self, query: str, extracts: List[Dict[str, Any]]) -> Dict[str, Any]:
        per_source: List[Dict[str, Any]] = []
        for e in extracts:
            url = e.get("url", "")
            dm = _domain(url)
            c = self.extract_claims(e.get("text", ""))
            per_source.append({
                "url": url,
                "domain": dm,
                "odds": c["odds"],
                "scores": c["scores"],
                "dates": c["dates"],
            })

        # Aggrega primo valore per tipo + relativo peso
        agg_vals: Dict[str, List[str]] = {"odds": [], "scores": [], "dates": []}
        agg_wts:  Dict[str, List[float]] = {"odds": [], "scores": [], "dates": []}

        for ps in per_source:
            dm = ps["domain"]
            # odds
            if ps["odds"]:
                agg_vals["odds"].append(ps["odds"][0])
                agg_wts["odds"].append(_weight_for(dm, "odds"))
            # scores
            if ps["scores"]:
                agg_vals["scores"].append(ps["scores"][0])
                agg_wts["scores"].append(_weight_for(dm, "scores"))
            # dates
            if ps["dates"]:
                agg_vals["dates"].append(ps["dates"][0])
                agg_wts["dates"].append(_weight_for(dm, "dates"))

        # Consenso pesato per tipo
        ratios: Dict[str, float] = {"odds": 0.0, "scores": 0.0, "dates": 0.0}
        majorants: Dict[str, str] = {"odds": "", "scores": "", "dates": ""}

        for k in ("odds", "scores", "dates"):
            r, maj = _weighted_majorant(agg_vals[k], agg_wts[k])
            ratios[k], majorants[k] = r, maj

        # Confidence complessiva: media pesata campi (odds e scores più pesanti)
        weights = {"odds": 0.45, "scores": 0.40, "dates": 0.15}
        conf_num = sum(ratios[k] * w for k, w in weights.items())
        conf_den = sum(weights.values()) or 1.0
        confidence = round(conf_num / conf_den, 3)

        # Conflitti (rispetto alla moda/majorant). Per odds applica tolleranza ±0.03
        conflicts: List[Dict[str, Any]] = []
        maj_odds = majorants["odds"]
        maj_score = majorants["scores"]
        maj_date = majorants["dates"]

        # parsing majorant odds per confronto in float
        maj_odds_f = None
        if maj_odds:
            try:
                maj_odds_f = float(maj_odds)
            except Exception:
                maj_odds_f = None

        for ps in per_source:
            diffs = []
            # odds
            if maj_odds and ps["odds"]:
                got = ps["odds"][0]
                try:
                    gf = float(got)
                    if maj_odds_f is None or not _close_enough(gf, maj_odds_f, tol=0.03):
                        diffs.append({"type": "odds", "got": got, "want": maj_odds, "delta": (None if maj_odds_f is None else round(gf - maj_odds_f, 3))})
                except Exception:
                    diffs.append({"type": "odds", "got": got, "want": maj_odds, "delta": None})
            # scores
            if maj_score and ps["scores"] and ps["scores"][0] != maj_score:
                diffs.append({"type": "scores", "got": ps["scores"][0], "want": maj_score})
            # dates
            if maj_date and ps["dates"] and ps["dates"][0] != maj_date:
                diffs.append({"type": "dates", "got": ps["dates"][0], "want": maj_date})

            if diffs:
                conflicts.append({"domain": ps["domain"], "url": ps["url"], "diffs": diffs})

        return {
            "validated": confidence >= 0.70,
            "confidence": confidence,
            "claims": {"majorants": majorants, "ratios": ratios},
            "conflicts": conflicts,
            "meta": {
                "field_weights": {
                    "odds": sum(agg_wts["odds"]) if agg_wts["odds"] else 0.0,
                    "scores": sum(agg_wts["scores"]) if agg_wts["scores"] else 0.0,
                    "dates": sum(agg_wts["dates"]) if agg_wts["dates"] else 0.0,
                }
            }
        }
