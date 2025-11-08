#!/usr/bin/env python3
# core/intent_classifier.py - Smart Intent Classification

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
    Classificatore di intent per routing intelligente.
    
    Decide se una query necessita:
    - Web search (info aggiornate)
    - Web read (lettura URL specifica)
    - Direct LLM (conoscenza interna)
    """
    
    # Indicatori di necessità web
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
    
    # Indicatori di conoscenza stabile
    STABLE_INDICATORS = [
        # Definizioni
        'cos\'è', 'cosa è', 'cosa sono', 'chi è', 'chi era',
        'definizione', 'significato', 'spiegami', 'spiega',
        
        # Concetti
        'come funziona', 'perché', 'differenza tra',
        'vantaggi', 'svantaggi', 'caratteristiche',
        
        # Istruzioni
        'come si fa', 'tutorial', 'guida', 'istruzioni',
        'come creare', 'come fare',
        
        # Storia
        'storia di', 'origine', 'inventato', 'scoperto',
        'anno', 'secolo', 'quando è nato', 'quando è morto',
    ]
    
    # ✅ DOMANDE TEMPORALI (FAST PATH)
    TIME_QUESTIONS = [
        'che ora', 'che ore', 'che giorno', 'che data',
        'quando è', 'che mese', 'in che anno', 'che anno',
        'quanti ne abbiamo', 'che giorno è oggi',
        'che giorno è domani', 'oggi che giorno',
    ]
    
    def __init__(self):
        """Inizializza classificatore"""
        pass
    
    def _extract_url(self, text: str) -> Optional[str]:
        """Estrae URL da testo"""
        match = re.search(r'https?://[^\s]+', text)
        return match.group(0) if match else None
    
    def _calculate_scores(self, text: str) -> Dict[str, float]:
        """Calcola score per ogni intent"""
        text_lower = text.lower()
        
        # Web score
        web_score = sum(
            1 for indicator in self.WEB_INDICATORS
            if indicator in text_lower
        )
        
        # Stable knowledge score
        stable_score = sum(
            1 for indicator in self.STABLE_INDICATORS
            if indicator in text_lower
        )
        
        return {
            'web_score': web_score,
            'stable_score': stable_score
        }
    
    def classify(self, text: str) -> Dict[str, Any]:
        """
        Classifica intent con analisi dettagliata.
        
        Args:
            text: Query dell'utente
        
        Returns:
            Dict con intent, confidence, params, analysis
        """
        
        text_lower = text.lower()
        
        # ✅ PRIORITY 1: Domande temporali semplici → DIRECT_LLM
        # Queste devono usare datetime context, NON web search
        if any(kw in text_lower for kw in self.TIME_QUESTIONS):
            return {
                "intent": Intent.DIRECT_LLM,
                "confidence": 1.0,
                "params": {"query": text},
                "reason": "Temporal query - use datetime context",
                "analysis": {
                    "web_score": 0,
                    "stable_score": 0,
                    "reasons": ["temporal_question"]
                }
            }
        
        # ✅ PRIORITY 2: URL detection → WEB_READ
        url = self._extract_url(text)
        if url:
            return {
                "intent": Intent.WEB_READ,
                "confidence": 1.0,
                "params": {"url": url},
                "reason": "URL detected"
            }
        
        # ✅ PRIORITY 3: Score-based classification
        scores = self._calculate_scores(text)
        web_score = scores['web_score']
        stable_score = scores['stable_score']
        
        # Reasons per debugging
        reasons = []
        
        # Decision logic
        if web_score > stable_score:
            # Web search vincente
            intent = Intent.WEB_SEARCH
            confidence = min(0.7 + (web_score * 0.1), 0.95)
            reasons.append(f"web_indicators={web_score}")
        
        elif stable_score > web_score:
            # Stable knowledge vincente
            intent = Intent.DIRECT_LLM
            confidence = min(0.7 + (stable_score * 0.1), 0.95)
            reasons.append(f"stable_indicators={stable_score}")
        
        else:
            # Pareggio → default based on query length
            if len(text.split()) <= 3:
                # Query brevi → più probabile che sia search
                intent = Intent.WEB_SEARCH
                confidence = 0.6
                reasons.append("short_query_ambiguous")
            else:
                # Query lunghe → più probabile conoscenza
                intent = Intent.DIRECT_LLM
                confidence = 0.6
                reasons.append("long_query_ambiguous")
        
        return {
            "intent": intent,
            "confidence": confidence,
            "params": {"query": text},
            "reason": f"Score-based: web={web_score} stable={stable_score}",
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
        # ✅ Temporal queries (dovrebbero essere DIRECT_LLM)
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
        
        # Print
        print(f"{status} '{query}'")
        print(f"   Expected: {expected_intent.value}")
        print(f"   Got:      {actual_intent.value} (conf: {confidence:.0%})")
        
        if 'analysis' in result:
            analysis = result['analysis']
            print(f"   Scores:   W={analysis['web_score']} S={analysis['stable_score']}")
            print(f"   Reasons:  {', '.join(analysis['reasons'])}")
        
        print()
    
    print("=" * 70)
    print(f"📊 RESULTS: {passed}/{len(test_cases)} passed ({100*passed//len(test_cases)}%)")
    
    if failed > 0:
        print(f"⚠️  {failed} test(s) failed")
    else:
        print("🎉 ALL TESTS PASSED!")
    
    print()
