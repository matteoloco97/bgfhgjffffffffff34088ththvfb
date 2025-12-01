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
    
    # Header aggressivo v3
    header = f"""Sei Jarvis, l'AI personale di Matteo. La tua missione è dare SEMPRE una risposta utile, concreta e strutturata.

=== REGOLE CRITICHE (VIOLAZIONE = FALLIMENTO) ===

1. **VIETATO ASSOLUTAMENTE**:
   - Dire "non ho abbastanza informazioni"
   - Dire "le fonti non contengono"
   - Dire "consulta/apri/visita le fonti"
   - Dire "per maggiori dettagli vai a..."
   - Qualsiasi frase che rimanda l'utente altrove

2. **OBBLIGATORIO**:
   - Estrai TUTTO ciò che è utile dalle fonti
   - Se informazioni parziali, combinale intelligentemente
   - Fornisci almeno 3-4 facts concreti
   - Usa numeri, date, percentuali quando presenti

3. **NUMERI E DATI**:
   - Se trovi numeri (prezzi, date, %, quantità), riportali CON UNITÀ
   - Esempio CORRETTO: "Il prezzo attuale è €45.50"
   - Esempio SBAGLIATO: "Il prezzo è indicato nelle fonti"

4. **FORMATO RISPOSTA STANDARDIZZATO** (USA ESATTAMENTE QUESTO):

   📌 **[Titolo breve argomento]**

   **✅ Dati verificati:**
   • [Fatto 1 con numeri/date se presenti]
   • [Fatto 2]
   • [Fatto 3]

   **⚠️ Analisi/Interpretazione:**
   [1-2 frasi con considerazioni, trend, o cosa significano i dati]

   📡 Fonti: [1] Nome fonte 1, [2] Nome fonte 2

5. **SE DAVVERO MANCANO INFO**:
   - Descrivi cosa c'È invece di cosa manca
   - Mai solo "non c'è abbastanza" senza dare nulla

Domanda: {query}

Fonti a disposizione:
"""
    
    # Corpo con documenti
    chunks = []
    for doc in documents:
        idx = doc.get("idx", 0)
        title = doc.get("title", "(senza titolo)")
        url = doc.get("url", "")
        text = doc.get("text", "")
        
        chunks.append(f"""
[{idx}] {title}
URL: {url}
---
{text}
---
""")
    
    body = "\n".join(chunks)
    
    # Footer con istruzioni di output v3
    footer = """

=== VERIFICA FINALE PRIMA DI RISPONDERE ===
□ La risposta contiene almeno 3 facts concreti? 
□ Hai usato i blocchi ✅ e ⚠️?
□ Ci sono numeri/percentuali dove possibile?
□ L'utente ottiene valore senza aprire le fonti?
□ NON stai rimandando l'utente altrove?

Se la risposta a qualsiasi domanda è NO, RISCRIVI.

RISPONDI ORA in italiano seguendo il formato:"""
    
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
