#!/usr/bin/env python3
# core/smart_intent_classifier.py — Zero-Web-by-Default, Deterministic & Robust (v4.2-PATCHED)
# 🔧 PATCH:
# - Biografie: DIRECT_LLM salvo presenza di trigger time-sensitive (→ WEB_SEARCH)
# - Evergreen/definizioni: override verso WEB_SEARCH se compaiono trigger di attualità (oggi/live/mercati/sport/meteo/orari)

import re
from typing import Dict, Any, Optional, List, Tuple

class SmartIntentClassifier:
    # ===== Normalizzatori / util =====
    _SPC   = re.compile(r"\s+")
    _PUNCT = re.compile(r"[\"'`´•·]+")

    @staticmethod
    def _norm(s: str) -> str:
        s = (s or "").strip()
        s = SmartIntentClassifier._PUNCT.sub("'", s)
        s = SmartIntentClassifier._SPC.sub(" ", s)
        return s

    # ===== Pattern =====
    # smalltalk (IT + EN)
    _SMALLTALK = re.compile(r"""(?ix)^\s*(
        ciao|salve|hey|hi|hello|hola|yo|
        buongiorno|buonasera|buonanotte|
        ci\s*sei\??|sei\s*online\??|come\s+va\??|tutto\s*bene\??|ok+|perfetto
    )\b""")

    # meta/capabilities
    _META = re.compile(r"""(?ix)\b(
        chi\s+sei|cosa\s+puoi\s+fare|come\s+funzioni|limitazioni|capacita'|capabilities|
        (puoi|riesci)\s+(navigare|usare|accedere)\s+(a|su)\s*internet|
        (collegarti|connetterti)\s+(a|su)\s*internet
    )\b""")

    # tempo interno (no web)
    _TIME = re.compile(r"""(?ix)\b(
        che\s*ora|che\s*ore|che\s*giorno|che\s*data|in\s*che\s*anno|che\s*mese|
        what\s*time|what\s*day|what\s*date|which\s*year|which\s*month
    )\b""")

    # task non-web (creativi / coding / traduzioni / spiegazioni)
    _NON_WEB_TASK = re.compile(r"""(?ix)\b(
        scrivi|riscrivi|riformula|tradu(ci|rre)|sintetizza(?!\s+fonti?)|
        genera|crea|progetta|bozza|template|prompt|
        spiega|insegnami|come\s+funziona|perche'|theory|concept|
        codice|snippet|regex|sql|python|javascript|bash|shell|docker|api|sdk
    )\b""")

    # 🔧 PATCHED: biografie (separate dalle altre evergreen)
    _BIOGRAPHY = re.compile(r"""(?ix)\b(
        chi\s+[eè]'?|chi\s+era|who\s+(is|was)|biografia\s+di|biography\s+of|
        dimmi\s+chi\s+è|tell\s+me\s+about
    )\b""")

    # Evergreen (definizioni/concepts) — ESCLUDE bio (gestite sopra)
    _EVERGREEN = re.compile(r"""(?ix)\b(
        cos['eè]|cosa\s+[eè]'?|cosa\s+sono|
        what\s+is|what\s+are|
        definizione|meaning|significato|differenza\s+tra|
        storia|origine|inventato|scoperto|nato
    )\b""")

    # segnali "dati che cambiano"
    _RECENCY = re.compile(r"(?i)\b(oggi|adesso|ora|in\s+tempo\s+reale|live|ultim[ei]|breaking|aggiornati?)\b")
    _MARKETS = re.compile(r"(?i)\b(prezzo|quotazione|tasso|valore|cambio|borsa|azioni?|indice|btc|eth|crypto|eur/?usd)\b")
    _WEATHER = re.compile(r"(?i)\b(meteo|tempo|previsioni|temperatura)\b")
    _SPORTS  = re.compile(r"(?i)\b(risultat[oi]|classifica|punteggio|partit[ae]|serie\s*a|champions|premier|nba|mlb|nhl|atp|wta)\b")
    _SCHEDULE= re.compile(r"(?i)\b(orari?|calendario|programma(zione)?)\b")

    # URL
    _URL_HTTP   = re.compile(r"https?://[^\s]+", re.I)
    _URL_WWW    = re.compile(r"\bwww\.[^\s]+\.[a-z]{2,}\b", re.I)
    _URL_DOMAIN = re.compile(r"(?i)(?<!@)\b([a-z0-9-]+\.)+[a-z]{2,}\b")  # dominio nudo (no email/IP)

    # intent espliciti
    _EXPLICIT_SEARCH = re.compile(r"""(?ix)\b(
        cerca|cercami|trova|verifica|controlla|fact[-\s]*check|
        fonti?|fonte|link|google(a|re)?|cercalo|search
    )\b""")
    _EXPLICIT_READ = re.compile(r"""(?ix)\b(
        leggi|riassumi|sintetizza|apri\s+(quest[oa]|il\s*link|la\s*pagina)|read\s+this|summariz(e|za)
    )\b""")

    # ——— util url ———
    def _extract_urls(self, t: str) -> List[str]:
        urls: List[str] = []
        urls += self._URL_HTTP.findall(t)
        urls += self._URL_WWW.findall(t)
        # domini nudi: validi solo se da soli o con segnali di lettura
        for m in self._URL_DOMAIN.findall(t):
            urls.append(m)
        # dedup preservando ordine
        seen = set(); out: List[str] = []
        for u in urls:
            if u not in seen:
                out.append(u); seen.add(u)
        return out

    # punteggio trigger "live"
    def _live_trigger_score(self, t: str, trace: List[str]) -> int:
        score = 0
        if self._RECENCY.search(t): score += 1; trace.append("RECENCY")
        if self._MARKETS.search(t): score += 1; trace.append("MARKETS")
        if self._WEATHER.search(t): score += 1; trace.append("WEATHER")
        if self._SPORTS.search(t):  score += 1; trace.append("SPORTS")
        if self._SCHEDULE.search(t):score += 1; trace.append("SCHEDULE")
        if t.strip().endswith("?"): score += 1; trace.append("QUESTION_MARK")
        return score

    def _is_smalltalk_like(self, t: str) -> bool:
        if len(t.split()) <= 2:
            return True
        return bool(self._SMALLTALK.search(t))

    def _has_time_sensitive(self, tl: str) -> bool:
        """True se compaiono trigger che richiedono web (attualità/variabili)."""
        return (
            self._RECENCY.search(tl)
            or self._MARKETS.search(tl)
            or self._WEATHER.search(tl)
            or self._SPORTS.search(tl)
            or self._SCHEDULE.search(tl)
        ) is not None

    # ——— entrypoint ———
    def classify(self, text: str) -> Dict[str, Any]:
        raw = (text or "")
        t = self._norm(raw)
        tl = t.lower()
        trace: List[str] = []

        # 0) smalltalk / very-short → LLM
        if self._is_smalltalk_like(tl):
            return {"intent": "DIRECT_LLM", "confidence": 0.95, "reason": "smalltalk_or_very_short",
                    "analysis": {"trace": ["SMALLTALK_OR_SHORT"], "text": t}}

        # 1) meta/capabilities → LLM
        if self._META.search(tl):
            return {"intent": "DIRECT_LLM", "confidence": 1.0, "reason": "meta_capabilities",
                    "analysis": {"trace": ["META"], "text": t}}

        # 2) tempo interno → LLM
        if self._TIME.search(tl):
            return {"intent": "DIRECT_LLM", "confidence": 1.0, "reason": "temporal_internal",
                    "analysis": {"trace": ["TIME_INTERNAL"], "text": t}}

        # 3) task non-web → LLM (a meno di richiesta esplicita di cercare)
        if self._NON_WEB_TASK.search(tl) and not self._EXPLICIT_SEARCH.search(tl):
            return {"intent": "DIRECT_LLM", "confidence": 0.92, "reason": "non_web_task",
                    "analysis": {"trace": ["NON_WEB_TASK"], "text": t}}

        # 4) URL presenti → WEB_READ se (http|www) oppure (dominio nudo + esplicita lettura)
        urls = self._extract_urls(t)
        if urls:
            has_http_or_www = (self._URL_HTTP.search(t) is not None) or (self._URL_WWW.search(t) is not None)
            if has_http_or_www or self._EXPLICIT_READ.search(tl):
                return {"intent": "WEB_READ", "confidence": 1.0, "reason": "url_present",
                        "url": urls[0], "analysis": {"trace": ["URL_PRESENT"], "urls": urls, "text": t}}
            trace.append("URL_NAKED_IGNORED")

        # 5) 🔧 Biografie: DIRECT_LLM salvo trigger time-sensitive → WEB_SEARCH
        if self._BIOGRAPHY.search(tl):
            if self._has_time_sensitive(tl):
                return {"intent": "WEB_SEARCH", "confidence": 0.88, "reason": "bio_time_sensitive",
                        "analysis": {"trace": ["BIO", "TIME_SENSITIVE"], "text": t}}
            return {"intent": "DIRECT_LLM", "confidence": 0.92, "reason": "biographical_knowledge",
                    "analysis": {"trace": ["BIO"], "text": t}}

        # 6) Evergreen/definizioni: default DIRECT_LLM, ma se attualità → WEB_SEARCH
        if self._EVERGREEN.search(tl):
            if self._has_time_sensitive(tl):
                return {"intent": "WEB_SEARCH", "confidence": 0.88, "reason": "evergreen_but_time_sensitive",
                        "analysis": {"trace": ["EVERGREEN", "TIME_SENSITIVE"], "text": t}}
            return {"intent": "DIRECT_LLM", "confidence": 0.9, "reason": "evergreen_definition",
                    "analysis": {"trace": ["EVERGREEN"], "text": t}}

        # 7) esplicito "cerca/verifica/fonte" → WEB_SEARCH
        if self._EXPLICIT_SEARCH.search(tl):
            return {"intent": "WEB_SEARCH", "confidence": 0.95, "reason": "explicit_search",
                    "analysis": {"trace": ["EXPLICIT_SEARCH"], "text": t}}

        # 8) trigger "live" (>=2) → WEB_SEARCH
        score = self._live_trigger_score(tl, trace)
        if score >= 2:
            return {"intent": "WEB_SEARCH", "confidence": 0.9, "reason": f"live_triggers[{score}]",
                    "analysis": {"trace": trace or ["LIVE_TRIGGERS"], "text": t}}

        # 9) fallback sicuro → LLM
        return {"intent": "DIRECT_LLM", "confidence": 0.7, "reason": "default_safe",
                "analysis": {"trace": trace or ["DEFAULT"], "text": t}}
