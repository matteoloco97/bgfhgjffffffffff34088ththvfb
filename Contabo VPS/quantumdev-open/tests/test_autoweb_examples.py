#!/usr/bin/env python3
"""
test_autoweb_examples.py
========================

Script di test per verificare il comportamento del sistema autoweb intelligente
con esempi reali dal problem statement.

Questo script mostra quali query dovrebbero triggerare autoweb e quali no.
"""

import sys
import os

# Add project root to path
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _PROJECT_ROOT)

from core.smart_intent_classifier import SmartIntentClassifier


def should_auto_search_semantic(text: str) -> tuple[bool, str]:
    """
    Analisi semantica per decidere se fare autoweb.
    (Imported logic from telegram_bot.py)
    
    NOTE: This function is intentionally duplicated here for test isolation.
    The tests should not depend on the implementation module to avoid
    circular dependencies and to allow independent testing of the logic.
    """
    text_lower = text.lower().strip()
    
    # Pattern semantici che indicano necessità di web search
    
    # 1. Eventi temporali (oggi, recente, ultimo, nuovo)
    temporal_indicators = [
        'oggi', 'ieri', 'recente', 'recentemente', 'ultimo', 'ultima',
        'nuovo', 'nuova', 'attuale', 'attuali', 'corrente',
        'questo mese', 'questa settimana', 'quest\'anno',
        'aggiornamento', 'aggiornamenti', 'novità'
    ]
    has_temporal = any(ind in text_lower for ind in temporal_indicators)
    
    # 2. Verbi di ricerca/scoperta
    search_verbs = [
        'cos\'è successo', 'cosa succede', 'cosa è cambiato',
        'scoperta', 'scoperte', 'annunciato', 'rivelato',
        'lanciato', 'rilasciato', 'pubblicato', 'ha annunciato'
    ]
    has_search_verb = any(verb in text_lower for verb in search_verbs)
    
    # 3. Prodotti/tech (spesso hanno aggiornamenti)
    tech_products = [
        'iphone', 'ipad', 'macbook', 'airpods',
        'samsung galaxy', 'pixel', 'android',
        'windows', 'macos', 'ios',
        'chatgpt', 'claude', 'gemini', 'copilot',
        'tesla', 'model', 'cybertruck'
    ]
    has_tech_product = any(prod in text_lower for prod in tech_products)
    
    # 4. Aziende tech/finance (info spesso cambiano)
    companies = [
        'openai', 'anthropic', 'google', 'microsoft', 'apple',
        'meta', 'facebook', 'amazon', 'nvidia', 'tesla',
        'spacex', 'twitter', 'x.com'
    ]
    has_company = any(comp in text_lower for comp in companies)
    
    # 5. Eventi geopolitici/finanziari
    events = [
        'guerra', 'conflitto', 'crisi', 'elezioni', 'voto',
        'mercato', 'borsa', 'inflazione', 'tassi',
        'fed', 'bce', 'governo', 'parlamento', 'situazione'
    ]
    has_event = any(ev in text_lower for ev in events)
    
    # 6. Query interrogative su fatti verificabili
    factual_patterns = [
        'quanto costa', 'quanto vale', 'quanti',
        'qual è il', 'quale è', 'chi è il', 'chi ha',
        'dove si trova', 'dove è', 'quando è',
        'come funziona il nuovo', 'cosa fa',
        'è vero che', 'è successo che'
    ]
    has_factual = any(pat in text_lower for pat in factual_patterns)
    
    # Decisione con priorità
    
    # Alta priorità: eventi temporali + verbi di ricerca/scoperta
    if has_temporal and (has_search_verb or has_factual):
        return True, "temporal_event_query"
    
    # Alta priorità: prodotti tech + indicatori temporali
    if has_tech_product and has_temporal:
        return True, "tech_product_update"
    
    # Media priorità: company + (temporal o factual o search verb)
    if has_company and (has_temporal or has_factual or has_search_verb):
        return True, "company_info_query"
    
    # Media priorità: eventi geopolitici/finanziari + temporal
    if has_event and has_temporal:
        return True, "geopolitical_or_financial_event"
    
    # Media priorità: eventi geopolitici/finanziari standalone (sempre search)
    if has_event and any(kw in text_lower for kw in ['guerra', 'conflitto', 'elezioni', 'mercato', 'borsa', 'inflazione']):
        return True, "geopolitical_or_financial_event"
    
    # Bassa priorità: query fattuali complesse
    if has_factual and len(text_lower.split()) >= 4:
        # Query factual lunga probabilmente richiede info aggiornate
        return True, "complex_factual_query"
    
    return False, "no_search_needed"


def test_query(query: str, classifier: SmartIntentClassifier):
    """Test a single query through both pattern matching and semantic analysis."""
    
    # Level 1: Pattern matching
    result = classifier.classify(query)
    intent = result.get("intent")
    confidence = result.get("confidence", 0)
    live_type = result.get("live_type")
    
    # Level 2: Semantic analysis
    should_search_semantic, semantic_reason = should_auto_search_semantic(query)
    
    # Determine final routing
    if intent == "WEB_SEARCH" and confidence >= 0.75:
        final_route = f"🌐 AUTOWEB (Pattern Match: {live_type or 'general'})"
    elif intent == "WEB_READ":
        final_route = "📄 AUTOWEB (URL Read)"
    elif should_search_semantic:
        final_route = f"🔍 AUTOWEB (Semantic: {semantic_reason})"
    else:
        final_route = "💬 CHAT (Direct LLM)"
    
    print(f"  Query: '{query}'")
    print(f"    → {final_route}")
    print()


def main():
    print("=" * 80)
    print("TEST ESEMPI: Jarvis Autoweb Intelligente")
    print("=" * 80)
    print()
    
    classifier = SmartIntentClassifier()
    
    # === Test cases dal problem statement ===
    
    print("📰 NEWS/EVENTI (dovrebbero triggerare autoweb):")
    print()
    test_query("Cos'è successo oggi in Ucraina?", classifier)
    test_query("Ultime notizie Tesla?", classifier)
    test_query("Cosa ha annunciato OpenAI?", classifier)
    
    print("\n" + "=" * 80 + "\n")
    print("💻 TECH/PRODOTTI (dovrebbero triggerare autoweb):")
    print()
    test_query("Come funziona il nuovo iPhone 16?", classifier)
    test_query("Recensioni MacBook M4?", classifier)
    test_query("Aggiornamenti Windows 11?", classifier)
    
    print("\n" + "=" * 80 + "\n")
    print("🌍 GEOPOLITICA/ECONOMIA (dovrebbero triggerare autoweb):")
    print()
    test_query("Situazione attuale Gaza?", classifier)
    test_query("Inflazione Italia oggi?", classifier)
    test_query("Risultati elezioni Francia?", classifier)
    
    print("\n" + "=" * 80 + "\n")
    print("❓ FACTUAL QUERIES (dovrebbero triggerare autoweb):")
    print()
    test_query("Quanto costa una Tesla Model 3?", classifier)
    test_query("Chi è il nuovo CEO di Twitter?", classifier)
    test_query("Dove si trova il nuovo data center Google?", classifier)
    
    print("\n" + "=" * 80 + "\n")
    print("✅ PATTERN ESISTENTI (dovrebbero continuare a funzionare):")
    print()
    test_query("Meteo Roma?", classifier)
    test_query("Prezzo Bitcoin?", classifier)
    test_query("Risultato Milan oggi", classifier)
    
    print("\n" + "=" * 80 + "\n")
    print("💬 CHAT NORMALE (NON dovrebbero triggerare autoweb):")
    print()
    test_query("Ciao come stai?", classifier)
    test_query("Spiegami la teoria della relatività", classifier)
    test_query("Scrivi codice Python per sorting", classifier)
    
    print("\n" + "=" * 80)
    print("✅ Test completato!")
    print("=" * 80)


if __name__ == "__main__":
    main()
