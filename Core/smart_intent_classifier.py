
#!/usr/bin/env python3
# core/smart_intent_classifier.py — Zero-Web-by-Default, Deterministic & Robust (v4)
# Obiettivi:
#  - Web disattivato per default (saluti, meta, tempo, evergreen, coding/creative → DIRECT_LLM)
#  - WEB_READ solo se c’è un URL *valido* o richiesta esplicita di leggere/riassumere
#  - WEB_SEARCH solo se (richiesta esplicita) OR (>=2 trigger forti di attualità/dati variabili)
#  - Anti-falsi positivi: “Ciao”, “Ok”, “ci sei?” ecc. non possono attivare il web
#  - Trace esplicativo per il debug (analysis.trace)

import re
from typing import Dict, Any, Optional, List, Tuple

class SmartIntentClassifier:
    # ===== Normalizzatori / util =====
    _SPC = re.compile(r"\s+")
    _PUNCT = re.compile(r"[“”\"'`´’•··]+")

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

    # evergreen / definizioni
    _EVERGREEN = re.compile(r"""(?ix)\b(
        cos['e]|cosa\s+e'|cosa\s+sono|chi\s+e'|chi\s+era|definizione|meaning|
        significato|differenza\s+tra|storia|origine|inventato|scoperto
    )\b""")

    # segnali “dati che cambiano”
    _RECENCY = re.compile(r"(?i)\b(oggi|adesso|ora|in\s+tempo\s+reale|live|ultim[ei]|breaking|aggiornati?)\b")
    _MARKETS = re.compile(r"(?i)\b(prezzo|quotazione|tasso|valore|cambio|borsa|azioni?|indice|btc|eth|crypto|eur/?usd)\b")
    _WEATHER = re.compile(r"(?i)\b(meteo|tempo|previsioni|temperatura)\b")
    _SPORTS  = re.compile(r"(?i)\b(risultat[oi]|classifica|punteggio|partit[ae]|serie\s*a|champions|premier|nba|mlb|nhl|atp|wta)\b")
    _SCHEDULE= re.compile(r"(?i)\b(orari?|calendario|programma(zione)?)\b")

    # URL
    _URL_HTTP = re.compile(r"https?://[^\s]+", re.I)
    _URL_WWW  = re.compile(r"\bwww\.[^\s]+\.[a-z]{2,}\b", re.I)
    # dominio “nudo” c.tld, evitando email/IP
    _URL_DOMAIN = re.compile(r"(?i)(?<!@)\b([a-z0-9-]+\.)+[a-z]{2,}\b")

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
        urls = []
        urls += self._URL_HTTP.findall(t)
        urls += self._URL_WWW.findall(t)
        # domini nudi: validi solo se da soli o con segnali di lettura
        for m in self._URL_DOMAIN.findall(t):
            # esclude parole come "ciao.it?" incollate? (regex già prudente)
            urls.append(m)
        # dedup preservando ordine
        seen = set()
        out = []
        for u in urls:
            if u not in seen:
                out.append(u); seen.add(u)
        return out

    # punteggio trigger “live”
    def _live_trigger_score(self, t: str, trace: List[str]) -> int:
        score = 0
        if self._RECENCY.search(t): score += 1; trace.append("RECENCY")
        if self._MARKETS.search(t): score += 1; trace.append("MARKETS")
        if self._WEATHER.search(t): score += 1; trace.append("WEATHER")
        if self._SPORTS.search(t):  score += 1; trace.append("SPORTS")
        if self._SCHEDULE.search(t):score += 1; trace.append("SCHEDULE")
        if t.strip().endswith("?"): score += 1; trace.append("QUESTION_MARK")
        return score

    # vincolo: non permettere WEB se smalltalk/very-short
    def _is_smalltalk_like(self, t: str) -> bool:
        if len(t.split()) <= 2:
            return True
        return bool(self._SMALLTALK.search(t))

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
            has_strong_url = any(self._URL_HTTP.search(t) or self._URL_WWW.search(t) for _ in [0])
            if has_strong_url or self._EXPLICIT_READ.search(tl):
                return {"intent": "WEB_READ", "confidence": 1.0, "reason": "url_present",
                        "url": urls[0], "analysis": {"trace": ["URL_PRESENT"], "urls": urls, "text": t}}
            # se solo dominio nudo senza richiesta esplicita: NON forzare web
            trace.append("URL_NAKED_IGNORED")

        # 5) evergreen / definizioni → LLM
        if self._EVERGREEN.search(tl):
            return {"intent": "DIRECT_LLM", "confidence": 0.9, "reason": "evergreen_definition",
                    "analysis": {"trace": ["EVERGREEN"], "text": t}}

        # 6) esplicito “cerca/verifica/fonte” → WEB_SEARCH
        if self._EXPLICIT_SEARCH.search(tl):
            return {"intent": "WEB_SEARCH", "confidence": 0.95, "reason": "explicit_search",
                    "analysis": {"trace": ["EXPLICIT_SEARCH"], "text": t}}

        # 7) trigger “live” (>=2) → WEB_SEARCH
        score = self._live_trigger_score(tl, trace)
        if score >= 2:
            return {"intent": "WEB_SEARCH", "confidence": 0.9, "reason": f"live_triggers[{score}]",
                    "analysis": {"trace": trace or ["LIVE_TRIGGERS"], "text": t}}

        # 8) fallback sicuro → LLM
        return {"intent": "DIRECT_LLM", "confidence": 0.7, "reason": "default_safe",
                "analysis": {"trace": trace or ["DEFAULT"], "text": t}}
