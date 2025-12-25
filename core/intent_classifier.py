#!/usr/bin/env python3
# core/intent_classifier.py — Smart Intent Classification (policy "come me")

import re
from enum import Enum
from typing import Dict, Any, Optional

class Intent(Enum):
    """Tipi di intent supportati"""
    WEB_SEARCH = "web_search"
    WEB_READ = "web_read"
    DIRECT_LLM = "direct_llm"

class IntentClassifier:
    """
    Classificatore di intent per routing intelligente "come me".

    Regole principali:
    - WEB_READ: se c'è un URL/domìnio o una richiesta esplicita di leggere/riassumere link
    - WEB_SEARCH: solo per info temporali/instabili, fact-check, richieste esplicite di cercare
    - DIRECT_LLM: small talk, compiti creativi/spiegazioni, traduzioni, contenuti evergreen, domande temporali (ora/giorno) che usano il datetime interno
    """

    # === Indicatori (compat per il vecchio scoring) ===

    WEB_INDICATORS = [
        # Temporali
        'oggi', 'adesso', 'ora', 'attuale', 'recente', 'ultimo', 'ultimi',
        'ieri', 'domani', 'questa settimana', 'questo mese',

        # Info che cambiano
        'meteo', 'tempo', 'previsioni', 'temperatura',
        'prezzo', 'quotazione', 'valore', 'costo',
        'news', 'notizie', 'ultime notizie', 'breaking',
        'risultati', 'classifica', 'punteggio', 'partita',
        'orari', 'apertura', 'chiusura',

        # Eventi
        'quando', 'data', 'evento', 'calendario',
        'uscita', 'rilascio', 'lancio',

        # Troubleshooting
        'errore', 'problema', 'non funziona', 'bug', 'fix',
        'come risolvere', 'soluzione', 'help',
    ]

    STABLE_INDICATORS = [
        # Definizioni/concetti
        "cos'è", "cosa è", "cosa sono", "chi è", "chi era",
        'definizione', 'significato', 'spiegami', 'spiega',
        'come funziona', 'perché', 'differenza tra',
        'vantaggi', 'svantaggi', 'caratteristiche',

        # Istruzioni
        'come si fa', 'tutorial', 'guida', 'istruzioni',
        'come creare', 'come fare',

        # Storia
        'storia di', 'origine', 'inventato', 'scoperto',
        'anno', 'secolo', 'quando è nato', 'quando è morto',
    ]

    # ✅ DOMANDE TEMPORALI (FAST PATH → LLM con datetime, NO web)
    TIME_QUESTIONS = [
        'che ora', 'che ore', 'che giorno', 'che data',
        'quando è', 'che mese', 'in che anno', 'che anno',
        'quanti ne abbiamo', 'che giorno è oggi',
        'che giorno è domani', 'oggi che giorno',
    ]

    # === Nuove euristiche "come me" ===
    SMALLTALK_RE = re.compile(r"""(?ix)^\s*(
        ciao|salve|hey|hi|hello|hola|
        buongiorno|buonasera|buonanotte|
        come\s+va|come\s+stai|tutto\s*bene|
        grazie(\s*mille)?|ok+|perfetto|va\s*bene|
        (:-?\)|;-\)|\^\^|😂|😅|😉|👍)
    )\b""")

    # Task che NON richiedono web (a meno che ci siano forti trigger temporali)
    NON_WEB_TASK_RE = re.compile(r"""(?ix)(
        (scrivi|riscrivi|riformula|tradu(ci|rre)|sintetizza(?!\s+fonti))|
        (genera|crea|progetta|bozza|template|prompt)|
        (spiega|insegnami|come\s+funziona|concetto|teoria|best\s*practice)|
        (codice|code|snippet|pseudocodice|regex|sql|python|javascript|bash)
    )""")

    # Trigger attualità / dati variabili
    WEB_TRIGGER_RE = re.compile(r"""(?ix)(
        (oggi|adesso|ora|in\s+tempo\s+reale|live|ultim[ei]|breaking|aggiornament[oi])|
        (prezzo|quotazione|tasso|meteo|risultat[oi]|classifica|calendario|orari?|programma(zione)?)|
        (news|novit[aà])|
        (btc|eth|sol|coin|crypto)|
        (serie\s*a|champions|europa\s+league|premier|nba|mlb|nhl|atp|wta)
    )""")

    # Richieste esplicite di cercare/leggere/citare
    WEB_FORCE_RE = re.compile(r"""(?ix)(
        (cerca|cercami|trova|verifica|controlla|fact\s*check|fonte|cita|link)|
        (riassumi|leggi)\s+(quest[oa]|questo\s*link|questa\s*pagina)
    )""")

    # URL o dominio testuale
    URL_LIKE_RE = re.compile(r"https?://|www\.|(\b[\w-]+\.\w{2,}\b)")

    def __init__(self):
        pass

    # ——— helpers ———
    def _extract_url(self, text: str) -> Optional[str]:
        """Estrae un URL o dominio chiaro dal testo."""
        m = re.search(r'https?://[^\s]+', text)
        if m:
            return m.group(0)
        # fallback: dominio nudo (es. example.com)
        m2 = re.search(r"\b[\w-]+\.\w{2,}\b", text)
        return m2.group(0) if m2 else None

    def _calculate_scores(self, text: str) -> Dict[str, float]:
        """Calcola score base (compat con versione precedente)."""
        tl = text.lower()
        web_score = sum(1 for ind in self.WEB_INDICATORS if ind in tl)
        stable_score = sum(1 for ind in self.STABLE_INDICATORS if ind in tl)
        return {'web_score': web_score, 'stable_score': stable_score}

    # ——— policy funcs ———
    def _is_smalltalk(self, text: str) -> bool:
        return bool(self.SMALLTALK_RE.search(text or ""))

    def _looks_like_url(self, text: str) -> bool:
        return bool(self.URL_LIKE_RE.search(text or ""))

    def _should_read_url(self, text: str) -> bool:
        """WEB_READ se c'è URL/domìnio o richiesta esplicita di leggere/riassumere link."""
        t = (text or "").strip()
        if self._looks_like_url(t):
            return True
        if self.WEB_FORCE_RE.search(t):
            return True
        return False

    def _has_strong_time_trigger(self, text: str) -> bool:
        return bool(self.WEB_TRIGGER_RE.search(text or "")) or (text or "").strip().endswith("?")

    def classify(self, text: str) -> Dict[str, Any]:
        """
        Classifica intent con analisi dettagliata.

        Returns:
            Dict con intent, confidence, params, reason, analysis
        """
        t = (text or "").strip()
        tl = t.lower()

        # ✅ PRIORITY 0: Query troppo corta → evita web
        if len(t) < 3:
            return {
                "intent": Intent.DIRECT_LLM,
                "confidence": 0.9,
                "params": {"query": text},
                "reason": "very-short",
                "analysis": {"web_score": 0, "stable_score": 0, "reasons": ["len<3"]}
            }

        # ✅ PRIORITY 1: Domande temporali semplici → DIRECT_LLM (datetime interno)
        if any(kw in tl for kw in self.TIME_QUESTIONS):
            return {
                "intent": Intent.DIRECT_LLM,
                "confidence": 1.0,
                "params": {"query": text},
                "reason": "temporal_question→datetime_context",
                "analysis": {"web_score": 0, "stable_score": 0, "reasons": ["temporal_question"]}
            }

        # ✅ PRIORITY 2: Small talk → DIRECT_LLM
        if self._is_smalltalk(t):
            return {
                "intent": Intent.DIRECT_LLM,
                "confidence": 0.95,
                "params": {"query": text},
                "reason": "smalltalk",
                "analysis": {"web_score": 0, "stable_score": 1, "reasons": ["smalltalk"]}
            }

        # ✅ PRIORITY 3: URL o richiesta esplicita di leggere/riassumere → WEB_READ
        url = self._extract_url(t)
        if self._should_read_url(t):
            return {
                "intent": Intent.WEB_READ,
                "confidence": 1.0 if url else 0.9,
                "params": {"url": url or t, "query": text},
                "reason": "explicit-url-or-read-request",
                "analysis": {"web_score": 1, "stable_score": 0, "reasons": ["url_or_read_request"]}
            }

        # ✅ PRIORITY 4: Se è un task NON-web (creativo/spiegazione/traduzione/codice)
        #     → DIRECT_LLM, a meno che ci siano forti trigger temporali (allora web)
        if self.NON_WEB_TASK_RE.search(t):
            if self._has_strong_time_trigger(t):
                return {
                    "intent": Intent.WEB_SEARCH,
                    "confidence": 0.85,
                    "params": {"query": text},
                    "reason": "non-web-task-but-strong-time-trigger",
                    "analysis": {"web_score": 1, "stable_score": 0, "reasons": ["time_trigger_overrides_nonweb"]}
                }
            return {
                "intent": Intent.DIRECT_LLM,
                "confidence": 0.9,
                "params": {"query": text},
                "reason": "non-web-task",
                "analysis": {"web_score": 0, "stable_score": 1, "reasons": ["non_web_task"]}
            }

        # ✅ PRIORITY 5: Attualità / numeri variabili / domanda aperta → WEB_SEARCH
        if self._has_strong_time_trigger(t):
            return {
                "intent": Intent.WEB_SEARCH,
                "confidence": 0.85,
                "params": {"query": text},
                "reason": "news/live/fact-check/informational",
                "analysis": {"web_score": 1, "stable_score": 0, "reasons": ["time_trigger_or_question_mark"]}
            }

        # ✅ PRIORITY 6: Fallback su scoring (compat con versione precedente)
        scores = self._calculate_scores(t)
        web_score = scores['web_score']
        stable_score = scores['stable_score']
        reasons = []

        if web_score > stable_score:
            intent = Intent.WEB_SEARCH
            confidence = min(0.7 + (web_score * 0.1), 0.95)
            reasons.append(f"web_indicators={web_score}")
        elif stable_score > web_score:
            intent = Intent.DIRECT_LLM
            confidence = min(0.7 + (stable_score * 0.1), 0.95)
            reasons.append(f"stable_indicators={stable_score}")
        else:
            # Pareggio: preferisci DIRECT_LLM se la query è "discorsiva",
            # altrimenti WEB_SEARCH se è una query breve secca.
            if len(t.split()) <= 3:
                intent = Intent.WEB_SEARCH
                confidence = 0.6
                reasons.append("short_query_ambiguous")
            else:
                intent = Intent.DIRECT_LLM
                confidence = 0.6
                reasons.append("long_query_ambiguous")

        return {
            "intent": intent,
            "confidence": confidence,
            "params": {"query": text},
            "reason": f"score-fallback: web={web_score} stable={stable_score}",
            "analysis": {
                "web_score": web_score,
                "stable_score": stable_score,
                "reasons": reasons
            }
        }


# === TESTS ===
if __name__ == "__main__":
    print("🎯 INTENT CLASSIFIER - TEST\n")
    print("=" * 70)

    classifier = IntentClassifier()

    test_cases = [
        # ✅ Temporal queries (DIRECT_LLM)
        ("Che ora è?", Intent.DIRECT_LLM),
        ("Che ore sono?", Intent.DIRECT_LLM),
        ("Che giorno è oggi?", Intent.DIRECT_LLM),
        ("In che anno siamo?", Intent.DIRECT_LLM),
        ("Che mese è?", Intent.DIRECT_LLM),

        # Web search (info aggiornate)
        ("meteo roma", Intent.WEB_SEARCH),
        ("prezzo bitcoin", Intent.WEB_SEARCH),
        ("risultati serie a oggi", Intent.WEB_SEARCH),
        ("ultime notizie", Intent.WEB_SEARCH),
        ("errore 502 nginx", Intent.WEB_SEARCH),

        # Direct LLM (conoscenza stabile)
        ("cos'è Python", Intent.DIRECT_LLM),
        ("chi era Einstein", Intent.DIRECT_LLM),
        ("differenza tra RAM e ROM", Intent.DIRECT_LLM),
        ("come funziona un motore", Intent.DIRECT_LLM),
        ("storia della Francia", Intent.DIRECT_LLM),

        # URL read
        ("https://example.com", Intent.WEB_READ),
        ("leggi https://news.com/article", Intent.WEB_READ),
    ]

    passed = 0
    failed = 0

    for query, expected_intent in test_cases:
        result = classifier.classify(query)
        actual_intent = result["intent"]
        confidence = result["confidence"]

        success = actual_intent == expected_intent
        status = "✅" if success else "❌"

        if success:
            passed += 1
        else:
            failed += 1

        print(f"{status} '{query}'")
        print(f"   Expected: {expected_intent.value}")
        print(f"   Got:      {actual_intent.value} (conf: {confidence:.0%})")

        if 'analysis' in result:
            analysis = result['analysis']
            print(f"   Scores:   W={analysis.get('web_score',0)} S={analysis.get('stable_score',0)}")
            print(f"   Reasons:  {', '.join(analysis.get('reasons',[]))}")

        print()

    print("=" * 70)
    print(f"📊 RESULTS: {passed}/{len(test_cases)} passed ({100*passed//len(test_cases)}%)")
    if failed > 0:
        print(f"⚠️  {failed} test(s) failed")
    else:
        print("🎉 ALL TESTS PASSED!")
    print()
