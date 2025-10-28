# core/intent_classifier.py
"""
Intent Classifier - Classificazione Autonoma Query Utente

Classifica automaticamente l'intent dell'utente in:
- WEB_READ: Lettura e riassunto URL
- WEB_SEARCH: Ricerca web per info fresche/aggiornate
- DIRECT_LLM: Risposta diretta dal modello

Logica 100% euristica, no ML, massima robustezza.
"""

import re
from enum import Enum
from typing import Dict, List, Optional
from dataclasses import dataclass


class Intent(Enum):
    """Tipologie di intent riconosciuti"""
    WEB_READ = "web_read"
    WEB_SEARCH = "web_search"
    DIRECT_LLM = "direct_llm"


@dataclass
class IntentDecision:
    """Risultato della classificazione"""
    intent: Intent
    confidence: float
    params: Dict[str, str]
    reasoning: str  # Per debug


class IntentClassifier:
    """
    Classificatore Euristico di Intent
    
    Regole di decisione:
    1. Se trova URL valido → WEB_READ
    2. Se rileva keywords temporali/info fresche → WEB_SEARCH
    3. Altrimenti → DIRECT_LLM
    """
    
    # Pattern URL (ottimizzato per recall alto)
    URL_PATTERN = re.compile(
        r'https?://[^\s<>"{}|\\^`\[\]]+',
        re.IGNORECASE
    )
    
    # Keywords che indicano necessità di info aggiornate
    FRESH_INFO_KEYWORDS = {
        # Temporali
        "oggi", "adesso", "ora", "attualmente", "corrente", "in questo momento",
        "ultime", "ultimi", "ultima", "ultimo", "recente", "recenti",
        "aggiornato", "aggiornata", "aggiornamenti", "update",
        
        # News/Eventi
        "notizie", "news", "breaking", "cronaca", "attualità",
        "uscite", "rilascio", "release", "annuncio", "lancio",
        
        # Dati Live
        "meteo", "tempo", "previsioni", "temperatura",
        "prezzo", "prezzi", "quotazione", "quote", "borsa", "crypto",
        "classifica", "risultati", "punteggio", "score",
        "partita", "match", "gara", "live",
        
        # Ricerche specifiche
        "cerca", "search", "trova", "google", "ricerca",
        "dimmi dove", "come posso trovare", "link",
        
        # Tempo reale
        "in tempo reale", "real time", "streaming", "diretta",
    }
    
    # Keywords per troubleshooting (spesso serve ricerca)
    TROUBLESHOOT_KEYWORDS = {
        "errore", "error", "bug", "problema", "issue",
        "non funziona", "doesn't work", "broken",
        "fix", "soluzione", "solution", "resolve",
        "502", "503", "404", "timeout", "crash",
        "stacktrace", "exception", "debug",
        "nginx", "apache", "kubernetes", "docker",
    }
    
    # Keywords che indicano domanda teorica/generale
    THEORETICAL_KEYWORDS = {
        "cos'è", "cosa è", "cos è", "what is", "che cos'è",
        "spiegami", "explain", "definizione", "definition",
        "come funziona", "how does", "how do",
        "perché", "perchè", "why", "quando", "when",
        "differenza tra", "difference between",
        "esempi di", "examples of",
        "tutorial", "guida", "guide",
    }
    
    def __init__(self):
        """Inizializza il classificatore"""
        pass
    
    def classify(self, text: str) -> Dict:
        """
        Classifica l'intent del testo
        
        Args:
            text: Testo da classificare
            
        Returns:
            Dict con chiavi:
            - intent: Intent enum
            - confidence: float (0.0-1.0)
            - params: dict con parametri specifici
            - reasoning: str (per debug)
        """
        if not text or not text.strip():
            return self._build_result(
                Intent.DIRECT_LLM,
                0.5,
                {},
                "Testo vuoto"
            )
        
        text_clean = text.strip()
        text_lower = text_clean.lower()
        
        # === REGOLA 1: URL presente → WEB_READ ===
        urls = self._extract_urls(text_clean)
        if urls:
            return self._build_result(
                Intent.WEB_READ,
                0.95,
                {"url": urls[0]},
                f"URL trovato: {urls[0]}"
            )
        
        # === REGOLA 2: Keywords info fresche → WEB_SEARCH ===
        fresh_score = self._score_keywords(text_lower, self.FRESH_INFO_KEYWORDS)
        troubleshoot_score = self._score_keywords(text_lower, self.TROUBLESHOOT_KEYWORDS)
        theoretical_score = self._score_keywords(text_lower, self.THEORETICAL_KEYWORDS)
        
        web_search_score = fresh_score + troubleshoot_score
        
        # Domande teoriche abbassano lo score web
        if theoretical_score > 0:
            web_search_score *= 0.5
        
        # Threshold per WEB_SEARCH
        if web_search_score >= 1.0:
            confidence = min(0.85, 0.6 + (web_search_score * 0.1))
            return self._build_result(
                Intent.WEB_SEARCH,
                confidence,
                {"query": text_clean},
                f"Keywords fresche: {web_search_score:.1f} punti"
            )
        
        # === REGOLA 3: Fallback → DIRECT_LLM ===
        # Ma riduci confidence se c'è qualche segnale ambiguo
        llm_confidence = 0.8
        reasoning = "Nessun segnale web"
        
        if web_search_score > 0.3:
            llm_confidence = 0.6
            reasoning = f"Ambiguo (web_score={web_search_score:.2f})"
        
        return self._build_result(
            Intent.DIRECT_LLM,
            llm_confidence,
            {},
            reasoning
        )
    
    def _extract_urls(self, text: str) -> List[str]:
        """Estrae URL validi dal testo"""
        urls = self.URL_PATTERN.findall(text)
        # Filtra URL validi (con TLD)
        valid = []
        for url in urls:
            # Deve avere almeno un punto dopo il dominio
            if '.' in url.split('/')[2] if len(url.split('/')) > 2 else False:
                valid.append(url)
        return valid
    
    def _score_keywords(self, text: str, keywords: set) -> float:
        """
        Conta keywords presenti nel testo
        
        Returns:
            Score float (num keywords matchate)
        """
        score = 0.0
        for kw in keywords:
            if kw in text:
                # Keywords più lunghe valgono di più
                score += 1.0 + (len(kw) / 50.0)
        return score
    
    def _build_result(
        self,
        intent: Intent,
        confidence: float,
        params: Dict[str, str],
        reasoning: str
    ) -> Dict:
        """Costruisce il dict di risultato nel formato atteso"""
        return {
            "intent": intent,
            "confidence": max(0.0, min(1.0, confidence)),
            "params": params,
            "reasoning": reasoning
        }


# === Utility per testing ===

def test_classifier():
    """Test suite per verificare il classificatore"""
    classifier = IntentClassifier()
    
    test_cases = [
        # WEB_READ
        ("Riassumi questo articolo: https://example.com/article", Intent.WEB_READ),
        ("Leggi https://wikipedia.org/wiki/Python", Intent.WEB_READ),
        ("http://news.com cosa dice?", Intent.WEB_READ),
        
        # WEB_SEARCH
        ("meteo oggi a Roma", Intent.WEB_SEARCH),
        ("ultime notizie breaking news", Intent.WEB_SEARCH),
        ("prezzo bitcoin adesso", Intent.WEB_SEARCH),
        ("risultati serie A oggi", Intent.WEB_SEARCH),
        ("errore 502 nginx come risolvere", Intent.WEB_SEARCH),
        ("cerca informazioni su kubernetes", Intent.WEB_SEARCH),
        
        # DIRECT_LLM
        ("cos'è un buco nero?", Intent.DIRECT_LLM),
        ("spiegami la relatività", Intent.DIRECT_LLM),
        ("come funziona la fotosintesi", Intent.DIRECT_LLM),
        ("scrivi una poesia sull'amore", Intent.DIRECT_LLM),
        ("calcola 2+2", Intent.DIRECT_LLM),
        ("ciao come stai?", Intent.DIRECT_LLM),
    ]
    
    print("🧪 TEST INTENT CLASSIFIER\n")
    print("=" * 80)
    
    passed = 0
    failed = 0
    
    for text, expected in test_cases:
        result = classifier.classify(text)
        intent = result["intent"]
        confidence = result["confidence"]
        reasoning = result["reasoning"]
        
        status = "✅" if intent == expected else "❌"
        if intent == expected:
            passed += 1
        else:
            failed += 1
        
        print(f"\n{status} Text: {text[:60]}")
        print(f"   Expected: {expected.value}")
        print(f"   Got: {intent.value} (conf: {confidence:.2f})")
        print(f"   Reasoning: {reasoning}")
    
    print("\n" + "=" * 80)
    print(f"\n📊 Results: {passed} passed, {failed} failed")
    print(f"   Success Rate: {passed/(passed+failed)*100:.1f}%")


if __name__ == "__main__":
    test_classifier()
