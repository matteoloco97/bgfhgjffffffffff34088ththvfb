#!/usr/bin/env python3
# core/smart_search.py - Smart Search Decision Engine (v2)

from __future__ import annotations
import re
from typing import Dict, List
from datetime import datetime

class SmartSearchEngine:
    """
    Sistema multi-layer per decidere quando serve web + hint per l'orchestrazione.
    Output extra:
      - topics_detected: List[str]
      - complexity: int 0..100
      - needs_timeliness: bool
      - decompose: bool (consiglia decomposition)
    """

    TEMPORAL_KEYWORDS = {
        'it': ['oggi','adesso','ora','attualmente','in questo momento','al momento','ieri','domani',
               'questa settimana','questo mese','quest\'anno','settimana scorsa','mese scorso','anno scorso',
               'ultimo','ultimi','ultima','ultime','aggiornato','attuale','in corso','in tempo reale','live'],
        'en': ['today','now','currently','yesterday','tomorrow','this week','this month','this year',
               'last week','last month','last year','recent','latest','current','updated','ongoing','real-time','live']
    }

    DYNAMIC_TOPICS = {
        'weather': {'keywords': ['meteo','tempo','previsioni','temperatura','rain','forecast','weather','che tempo fa'], 'weight': 40},
        'news':    {'keywords': ['notizie','news','breaking','ultime','cronaca','headlines','updates','cosa succede'], 'weight': 45},
        'prices':  {'keywords': ['prezzo','costa','quotazione','quanto costa','price','value','worth','quanto vale'], 'weight': 35},
        'sports':  {'keywords': ['partita','risultato','classifica','marcatori','match','score','league','serie a','champions'], 'weight': 40},
        'stocks':  {'keywords': ['borsa','azioni','nasdaq','bitcoin','crypto','ethereum','market','btc','eth'], 'weight': 35},
        'events':  {'keywords': ['quando apre','orari','programma','calendar','schedule','evento','eventi'], 'weight': 30},
        'traffic': {'keywords': ['traffico','code','incidente','viabilità','traffic','jam'], 'weight': 35},
        'realtime':{'keywords': ['streaming','diretta','watch live','live','in diretta','in tempo reale'], 'weight': 45},
        'health':  {'keywords': ['sintomi','malattia','farmaco','dose','posologia','guidelines','salute'], 'weight': 30},
        'finance': {'keywords': ['fed','inflazione','tasso','pil','earnings','guidance','economia'], 'weight': 30},
        'tech':    {'keywords': ['rilascio','release','versione','changelog','patch','v','build','aggiornamento'], 'weight': 25},
        'facts':   {'keywords': ['statistiche','dati','cifre','numeri','percentuale','statistics','data'], 'weight': 30},
    }

    STABLE_KEYWORDS = [
        'cos\'è','cos è','cosa è','chi è','chi era','what is','who is','what are',
        'spiega','definisci','definizione','explain','define','differenza tra','difference between',
        'come funziona','how does','how to','perché','why','storia','origini','theory','concept','principle'
    ]

    HISTORICAL_KEYWORDS = [
        'nato','morto','fondato','fondazione','iniziato','finito','accaduto','guerra','battaglia','scoperta',
        'born','died','founded','started','ended','happened','war','battle','discovery'
    ]

    def __init__(self):
        self.temporal_pattern = self._compile(r'\b(' + '|'.join(map(re.escape,
            self.TEMPORAL_KEYWORDS['it'] + self.TEMPORAL_KEYWORDS['en'])) + r')\b')
        self.stable_pattern   = self._compile(r'\b(' + '|'.join(map(re.escape, self.STABLE_KEYWORDS)) + r')\b')
        self.historical_pattern = self._compile(r'\b(' + '|'.join(map(re.escape, self.HISTORICAL_KEYWORDS)) + r')\b')

    def _compile(self, pattern: str) -> re.Pattern:
        return re.compile(pattern, re.IGNORECASE)

    # --- helpers ---
    def _detect_topics(self, q: str) -> List[str]:
        found = []
        for t, cfg in self.DYNAMIC_TOPICS.items():
            if any(k in q for k in cfg['keywords']):
                found.append(t)
        return found

    def _complexity(self, q: str) -> int:
        # lunghezza + connettivi + numeri = maggiore complessità
        words = len(q.split())
        conn = len(re.findall(r'\b(e|ed|ma|perchè|perche|perché|quindi|tuttavia|and|or|but|because|mentre|invece)\b', q))
        nums = len(re.findall(r'\d', q))
        punct = len(re.findall(r'[;:()\[\],]', q))
        # ENHANCED: Considera anche domande multiple e comparazioni
        questions = len(re.findall(r'\?', q))
        comparisons = len(re.findall(r'\b(vs|versus|contro|meglio|migliore|differenza|confronto|compare)\b', q, re.I))
        score = min(100, words*2 + conn*10 + nums*4 + punct*3 + questions*8 + comparisons*12)
        return score

    # --- main ---
    def analyze(self, query: str) -> Dict:
        q = query.lower().strip()
        web_score = 0
        stable_score = 0
        reasons: List[str] = []

        if self.temporal_pattern.search(q):
            web_score += 40; reasons.append("⏰ Indicatori temporali")

        topics = self._detect_topics(q)
        for t in topics:
            web_score += self.DYNAMIC_TOPICS[t]['weight']
            reasons.append(f"📊 Topic dinamico: {t}")
            # non break: più topic aumentano web_score

        if self.stable_pattern.search(q):
            stable_score += 35; reasons.append("📚 Domanda concettuale")
        if self.historical_pattern.search(q):
            stable_score += 30; reasons.append("🏛️ Storico")

        if q.startswith(('quando ', 'when ')):
            if self.historical_pattern.search(q):
                stable_score += 20; reasons.append("📜 Quando storico")
            else:
                web_score += 25; reasons.append("📅 Quando situazionale")
        if q.startswith(('dove ', 'where ')):
            web_score += 20; reasons.append("📍 Localizzazione")

        if re.search(r'https?://', query):  # qualsiasi URL → WEB_READ a valle
            web_score += 50; reasons.append("🔗 URL presente")

        if len(q.split()) <= 3 and not self.temporal_pattern.search(q):
            stable_score += 15; reasons.append("🔤 Query breve (prob. definizione)")

        current_year = datetime.now().year
        for y_s in re.findall(r'\b(20\d{2})\b', q):
            y = int(y_s)
            if y >= current_year - 1:
                web_score += 15; reasons.append(f"📆 Anno recente: {y}")
            elif y < current_year - 5:
                stable_score += 10; reasons.append(f"📜 Anno passato: {y}")

        if re.search(r'\b(come si fa|come posso|how can i|how do i|mostrami|show me)\b', q):
            stable_score += 20; reasons.append("🛠️ How-to/Tutorial")

        needs_web = web_score > stable_score
        total = max(1, web_score + stable_score)
        confidence = max(web_score, stable_score) / total

        complexity = self._complexity(q)
        decompose = complexity >= 55 and not re.search(r'^(cos\'?è|cosa|what is|definizione)', q)
        needs_timeliness = bool(self.temporal_pattern.search(q) or ('news' in topics))

        return {
            'needs_web_search': needs_web,
            'confidence': confidence,
            'web_score': web_score,
            'stable_score': stable_score,
            'reasons': reasons,
            'decision': 'WEB_SEARCH' if needs_web else 'DIRECT_LLM',
            'query': query,
            'topics_detected': topics,
            'complexity': complexity,
            'needs_timeliness': needs_timeliness,
            'decompose': decompose
        }
