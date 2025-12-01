#!/usr/bin/env python3
"""
synthesis_prompt_v2.py
======================
Prompt di sintesi AGGRESSIVO che estrae SEMPRE valore dalle fonti.

Cambio filosofico:
- PRIMA: "Se l'info non c'è, dillo" → risposte evasive
- ADESSO: "Estrai TUTTO ciò che è utile, anche parzialmente correlato"

Versione v3: Aggiunge formato standardizzato con blocchi ✅/⚠️ e
richiede sempre numeri, percentuali, date concrete.

Versione v4: Formato TL;DR + bullet + fonti per risposte secche.
"""


def build_aggressive_synthesis_prompt(query: str, documents: list) -> str:
    """
    Costruisce un prompt che FORZA l'LLM a estrarre valore,
    anche da informazioni parziali o indirettamente collegate.
    
    Args:
        query: Domanda utente originale
        documents: Lista di dict con {idx, title, url, text}
    
    Returns:
        Prompt completo per il modello
    """
    
    # Header aggressivo v4 - formato TL;DR
    header = f"""Sei Jarvis, l'AI personale di Matteo. Dai SEMPRE risposte SECCHE e CONCRETE.

=== REGOLE CRITICHE ===

1. **FORMATO OBBLIGATORIO**:

📌 **TL;DR:** [1-2 frasi di sintesi diretta]

**✅ Punti chiave:**
1. [Fatto concreto con numero/data se presente]
2. [Fatto concreto]
3. [Fatto concreto]

**📡 Fonti:** [1] Nome1, [2] Nome2

**⚠️ Nota:** [Solo se necessario, max 1 riga]

2. **VIETATO ASSOLUTAMENTE**:
   - "Non ho abbastanza informazioni"
   - "Le fonti sono parziali"
   - "Consulta/apri le fonti per..."
   - "Potrebbe essere/tuttavia/forse" (sii diretto!)
   - Più di 6 bullet points
   - Frasi da manuale scolastico

3. **OBBLIGATORIO**:
   - TL;DR breve e diretto (max 2 frasi)
   - 3-6 bullet points NUMERATI con fatti concreti
   - Numeri CON UNITÀ quando presenti
   - Lista fonti a fine risposta

Domanda: {query}

Fonti:
"""
    
    # Corpo con documenti (compatto)
    chunks = []
    for doc in documents:
        idx = doc.get("idx", 0)
        title = doc.get("title", "(senza titolo)")[:60]
        text = doc.get("text", "")[:800]  # Limita testo
        
        chunks.append(f"[{idx}] {title}\n{text}\n---")
    
    body = "\n".join(chunks)
    
    # Footer minimal
    footer = """

RISPONDI ORA usando il formato TL;DR + bullet + fonti:"""
    
    return header + body + footer


def build_code_synthesis_prompt(query: str, documents: list) -> str:
    """
    Prompt specializzato per sintesi di documentazione/tutorial di codice.
    
    Args:
        query: Domanda utente su coding/programmazione
        documents: Lista di dict con {idx, title, url, text}
    
    Returns:
        Prompt ottimizzato per contenuti tecnici
    """
    header = f"""Sei Jarvis, esperto programmatore. Sintetizza la documentazione tecnica in modo pratico.

REGOLE:
1. Estrai i concetti chiave e mostra esempi di codice quando presenti
2. Organizza la risposta per livello (base → avanzato)
3. Se ci sono snippet di codice, includili formattati
4. Dai priorità a soluzioni pratiche vs teoria

Domanda: {query}

Fonti tecniche:
"""

    chunks = []
    for doc in documents:
        idx = doc.get("idx", 0)
        title = doc.get("title", "(senza titolo)")
        text = doc.get("text", "")
        chunks.append(f"""
[{idx}] {title}
---
{text}
---
""")
    
    body = "\n".join(chunks)
    
    footer = """

FORMATO RISPOSTA:

📌 **[Argomento tecnico]**

**✅ Concetti chiave:**
• [Concetto 1]
• [Concetto 2]

**💻 Esempio pratico:**
```
[codice se presente nelle fonti]
```

**⚠️ Note importanti:**
[Tips, gotchas, best practices]

RISPONDI ORA:"""

    return header + body + footer


def build_market_synthesis_prompt(query: str, documents: list) -> str:
    """
    Prompt specializzato per sintesi dati finanziari/mercati.
    
    Args:
        query: Domanda su prezzi, mercati, finanza
        documents: Lista di dict con {idx, title, url, text}
    
    Returns:
        Prompt ottimizzato per dati finanziari
    """
    header = f"""Sei Jarvis, analista finanziario. Sintetizza i dati di mercato in modo preciso.

REGOLE:
1. SEMPRE riportare prezzi/quotazioni con valuta e timestamp
2. Mostrare variazioni % (24h, 7d, YTD se disponibili)
3. Evidenziare trend (rialzo/ribasso)
4. Mai arrotondare troppo i numeri - precisione conta

Domanda: {query}

Fonti finanziarie:
"""

    chunks = []
    for doc in documents:
        idx = doc.get("idx", 0)
        title = doc.get("title", "(senza titolo)")
        text = doc.get("text", "")
        chunks.append(f"""
[{idx}] {title}
---
{text}
---
""")
    
    body = "\n".join(chunks)
    
    footer = """

FORMATO RISPOSTA:

📈 **[Asset/Mercato]** – quotazione live

**✅ Dati di mercato:**
• Prezzo: [valore con valuta]
• Variazione 24h: [+/-X.XX%]
• Volume/Market Cap: [se disponibile]

**⚠️ Contesto:**
[Trend, supporti/resistenze, eventi che impattano]

📡 Fonti: [lista numerata]

RISPONDI ORA:"""

    return header + body + footer


# ===== ESEMPI DI USO =====

def test_examples():
    """
    Mostra come il nuovo prompt gestisce casi critici
    """
    
    # Caso 1: Meteo Roma domani
    docs_meteo = [
        {
            "idx": 1,
            "title": "ILMETEO.it - Previsioni Italia",
            "url": "https://www.ilmeteo.it/",
            "text": "Previsioni meteo per l'Italia. Roma: temperatura massima 18°C, minima 12°C. Cielo sereno con nubi sparse nel pomeriggio. Vento debole da nord-est."
        },
        {
            "idx": 2,
            "title": "3B Meteo",
            "url": "https://www.3bmeteo.com/",
            "text": "Situazione meteo Italia centro-sud. Per Roma attese condizioni di bel tempo con temperature in linea con la stagione."
        }
    ]
    
    prompt_meteo = build_aggressive_synthesis_prompt(
        "meteo Roma domani", 
        docs_meteo
    )
    
    print("="*80)
    print("ESEMPIO 1: Meteo Roma domani")
    print("="*80)
    print(prompt_meteo)
    print("\n" + "="*80 + "\n")
    
    # Caso 2: Python tutorial
    docs_python = [
        {
            "idx": 1,
            "title": "Python Tutorial - Official Docs",
            "url": "https://docs.python.org/3/tutorial/",
            "text": "Python è un linguaggio interpretato, interattivo e orientato agli oggetti. Integra moduli, eccezioni, typing dinamico e classi. Python combina potenza con sintassi chiara."
        },
        {
            "idx": 2,
            "title": "Real Python Tutorials",
            "url": "https://realpython.com/",
            "text": "Tutorial Python per principianti e avanzati. Copre: variabili, funzioni, loop, OOP, web development con Django/Flask."
        }
    ]
    
    prompt_python = build_code_synthesis_prompt(
        "python tutorial",
        docs_python
    )
    
    print("="*80)
    print("ESEMPIO 2: Python tutorial (code synthesis)")
    print("="*80)
    print(prompt_python)
    print("\n" + "="*80 + "\n")
    
    # Caso 3: Prezzo Bitcoin
    docs_crypto = [
        {
            "idx": 1,
            "title": "CoinMarketCap - Bitcoin",
            "url": "https://coinmarketcap.com/currencies/bitcoin/",
            "text": "Bitcoin (BTC) price today is $43,250.00 with a 24-hour trading volume of $28B. BTC is up 2.5% in the last 24 hours. Market cap: $847B."
        }
    ]
    
    prompt_crypto = build_market_synthesis_prompt(
        "prezzo bitcoin oggi",
        docs_crypto
    )
    
    print("="*80)
    print("ESEMPIO 3: Prezzo Bitcoin (market synthesis)")
    print("="*80)
    print(prompt_crypto)
    print("\n" + "="*80 + "\n")


if __name__ == "__main__":
    test_examples()
