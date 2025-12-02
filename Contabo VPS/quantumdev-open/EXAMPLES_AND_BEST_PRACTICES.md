# 💡 EXAMPLES AND BEST PRACTICES - QuantumDev Max

Esempi pratici e best practices per sfruttare al meglio QuantumDev Max.

---

## 📑 Indice

1. [Esempi Conversational Memory](#-conversational-memory)
2. [Esempi Function Calling](#-function-calling)
3. [Esempi Reasoning Traces](#-reasoning-traces)
4. [Esempi Artifacts](#-artifacts)
5. [Patterns Avanzati](#-patterns-avanzati)
6. [Best Practices](#-best-practices)
7. [Anti-Patterns da Evitare](#-anti-patterns)

---

## 🧠 Conversational Memory

### Esempio 1: Multi-turn Code Development

```
👤 User: Devo creare un'API REST per un todo app

🤖 Jarvis: Perfetto! Quale framework preferisci? Ho esperienza con FastAPI, 
   Flask, Express.js, Django REST...

👤 User: FastAPI

🤖 Jarvis: Ottimo. E per il database? Posso suggerirti SQLite per sviluppo 
   locale, PostgreSQL per produzione, o MongoDB se preferisci NoSQL.

👤 User: SQLite va bene per ora

🤖 Jarvis: [RICORDA: FastAPI + SQLite]
   Ecco la struttura base:
   
   [Creates code artifact with full CRUD API]
   
   Vuoi che aggiunga autenticazione JWT?
   
👤 User: Sì, e anche i test

🤖 Jarvis: [RICORDA: vuole auth + test]
   Aggiungo:
   1. Auth JWT con python-jose
   2. Test con pytest + httpx
   
   [Creates updated artifact]
```

**Cosa succede dietro:**
- Sessione salvata con tutti i turni
- Contesto mantenuto attraverso la conversazione
- Auto-summarization se supera 20 turni

---

### Esempio 2: Research con Memoria

```
👤 User: Sto studiando transformer architecture

🤖 Jarvis: I Transformer sono un'architettura rivoluzionaria introdotta 
   nel paper "Attention Is All You Need" (2017)...
   
   [Salva in memoria: utente studia transformers]

👤 User: Spiegami il meccanismo di attention

🤖 Jarvis: [Recall: sta studiando transformers]
   L'attention mechanism nei Transformer funziona così:
   - Query, Key, Value vectors
   - Scaled dot-product attention
   - Multi-head attention per catturare diverse relazioni...

👤 User: Come si collega a BERT?

🤖 Jarvis: [Recall: transformers, attention]
   BERT usa l'encoder dei Transformer:
   - Bidirectional (vs GPT che è unidirettional)
   - Masked Language Model per pre-training...
   
   Vuoi che ti spieghi le differenze con GPT?
```

---

### Esempio 3: Preferenze Persistenti

```
👤 User: Preferisco risposte brevi e in italiano

🤖 Jarvis: [Salva preferenza: risposte brevi, italiano]
   Perfetto! D'ora in poi sarò conciso.

[... 2 giorni dopo ...]

👤 User: Explain machine learning

🤖 Jarvis: [Recall: preferisce italiano, risposte brevi]
   Il Machine Learning è l'apprendimento automatico: 
   algoritmi che migliorano con l'esperienza sui dati.
   
   Tre tipi principali:
   • Supervised: impara da esempi etichettati
   • Unsupervised: trova pattern nei dati
   • Reinforcement: impara da feedback
```

---

## 🔧 Function Calling

### Esempio 1: Multi-tool Automatico

```
👤 User: Quanto costa Bitcoin adesso e calcola quanto varrebbe investire €1000

🤖 Jarvis: [Analisi: serve prezzo BTC + calcolo]
   
   [Tool: price_lookup] → BTC = $42,500
   [Tool: calculator] → €1000 * (1/42500) = 0.0235 BTC
   
   Bitcoin è a $42,500. Con €1000 (≈$1,100) potresti comprare 
   circa 0.026 BTC.

👤 User: E se investissi in ETH invece?

🤖 Jarvis: [Recall: sta confrontando crypto]
   
   [Tool: price_lookup] → ETH = $2,200
   [Tool: calculator] → $1100 / 2200 = 0.5 ETH
   
   Con lo stesso importo compreresti 0.5 ETH.
   
   Confronto:
   • BTC: 0.026 coin
   • ETH: 0.5 coin
   
   ETH ti dà più "unità" ma il valore è equivalente.
```

---

### Esempio 2: Research + Code

```
👤 User: Cerca le best practices per async Python e scrivi un esempio

🤖 Jarvis: [Analisi: web_search + code_generator]
   
   [Tool: web_search] → Found 5 sources on async Python
   [Tool: code_generator] → Creating example
   
   Best practices da fonti autorevoli:
   1. Usa `asyncio.gather()` per task paralleli
   2. Evita blocking I/O nel event loop
   3. Usa context managers con `async with`
   
   📦 Artifact: async_example.py
   ```python
   import asyncio
   import aiohttp
   
   async def fetch_url(session, url):
       async with session.get(url) as response:
           return await response.json()
   
   async def main():
       urls = ['https://api1.example', 'https://api2.example']
       async with aiohttp.ClientSession() as session:
           results = await asyncio.gather(*[
               fetch_url(session, url) for url in urls
           ])
       return results
   
   if __name__ == "__main__":
       asyncio.run(main())
   ```
```

---

### Esempio 3: Scheduled Task

```
👤 User: A che ora gioca la Juve domani e dammi le quote

🤖 Jarvis: [Analisi: schedule_lookup + potenzialmente betting data]
   
   [Tool: schedule_lookup] → Juventus vs Milan, 20:45
   [Tool: web_search] → Odds: Juve 2.10, Draw 3.40, Milan 3.50
   
   📅 Juventus vs Milan
   🕐 Domani ore 20:45
   
   Quote (indicative):
   • Juventus: 2.10
   • Pareggio: 3.40
   • Milan: 3.50
   
   ⚠️ Le quote cambiano in tempo reale, verifica sul bookmaker.
```

---

## 💭 Reasoning Traces

### Esempio: Debug Trasparente

```
👤 User: /think Perché il prezzo di Bitcoin è volatile?

🤖 Jarvis: 
   🧠 **Reasoning Trace**
   
   🔍 **Analysis** (12ms)
   Query richiede spiegazione economica/finanziaria.
   Non serve web search, è conoscenza generale.
   
   📋 **Planning** (5ms)
   Strategia: DIRECT_LLM con conoscenza economica.
   
   ⚡ **Execution** (0ms)
   Nessun tool necessario.
   
   ✨ **Synthesis** (845ms)
   Generazione risposta...
   
   ✅ **Total: 862ms**
   
   📝 **Response:**
   Bitcoin è volatile per diversi fattori:
   
   1. **Supply limitata** (21M max) amplifica movimenti
   2. **Mercato giovane** con meno liquidità
   3. **Speculazione** alta percentuale di trading
   4. **News-driven** reazioni forti a notizie
   5. **Whale movements** grandi holder muovono il mercato
```

---

### Esempio: Tool Chain Visibility

```
👤 User: /think Confronta meteo Roma vs Milano oggi

🤖 Jarvis:
   🧠 **Reasoning Trace**
   
   🔍 **Analysis** (15ms)
   Query richiede dati live da 2 città.
   Tool: weather (x2, parallel)
   
   📋 **Planning** (8ms)
   Strategia: TOOL_ASSISTED
   Tools: weather(Roma), weather(Milano) in parallelo
   
   ⚡ **Execution** (1250ms)
   • weather(Roma) → ☀️ 18°C
   • weather(Milano) → 🌧️ 12°C
   
   🤔 **Reflection** (5ms)
   Entrambi i tool hanno risposto, dati completi.
   
   ✨ **Synthesis** (320ms)
   Costruzione tabella comparativa...
   
   ✅ **Total: 1598ms**
   
   📝 **Response:**
   | Città | Temp | Condizioni |
   |-------|------|------------|
   | Roma | 18°C | ☀️ Sole |
   | Milano | 12°C | 🌧️ Pioggia |
   
   Roma è più calda di 6°C oggi!
```

---

## 📦 Artifacts

### Esempio 1: Code Artifact

```
👤 User: Scrivi una classe Python per gestire una coda prioritaria

🤖 Jarvis:
   📦 **Priority Queue Implementation** (v1)
   Type: code | Language: python
   
   ```python
   import heapq
   from typing import Any, Optional
   from dataclasses import dataclass, field
   
   @dataclass(order=True)
   class PriorityItem:
       priority: int
       item: Any = field(compare=False)
   
   class PriorityQueue:
       def __init__(self):
           self._heap: list = []
           self._counter = 0
       
       def push(self, item: Any, priority: int = 0) -> None:
           heapq.heappush(self._heap, PriorityItem(priority, item))
           self._counter += 1
       
       def pop(self) -> Optional[Any]:
           if self._heap:
               return heapq.heappop(self._heap).item
           return None
       
       def peek(self) -> Optional[Any]:
           return self._heap[0].item if self._heap else None
       
       def __len__(self) -> int:
           return len(self._heap)
       
       def __bool__(self) -> bool:
           return bool(self._heap)
   ```
   
   Artifact ID: `art_a1b2c3d4e5f6`
   
   Vuoi che aggiunga metodi per update priority?
```

---

### Esempio 2: Table Artifact

```
👤 User: Crea una tabella comparativa GPU per ML

🤖 Jarvis:
   📦 **GPU Comparison for ML** (v1)
   Type: table
   
   | GPU | VRAM | Tensor Cores | Price | Best For |
   |-----|------|--------------|-------|----------|
   | RTX 3090 | 24GB | 328 | $1,500 | Training medium models |
   | RTX 4090 | 24GB | 512 | $1,600 | Fast inference |
   | A100 | 40/80GB | 432 | $10,000+ | Enterprise training |
   | RTX 8000 | 48GB | 576 | $5,500 | Large models, budget |
   | H100 | 80GB | 528 | $25,000+ | State-of-art training |
   
   Artifact ID: `art_x1y2z3w4v5u6`
   
   Per QuantumDev Max, la RTX 8000 con 48GB VRAM è ottimale
   per Qwen 32B AWQ.
```

---

### Esempio 3: JSON Artifact

```
👤 User: Genera lo schema JSON per un'API di e-commerce

🤖 Jarvis:
   📦 **E-commerce API Schema** (v1)
   Type: json | Language: json
   
   ```json
   {
     "openapi": "3.0.0",
     "info": {
       "title": "E-commerce API",
       "version": "1.0.0"
     },
     "paths": {
       "/products": {
         "get": {
           "summary": "List products",
           "parameters": [
             {"name": "category", "in": "query", "type": "string"},
             {"name": "limit", "in": "query", "type": "integer"}
           ],
           "responses": {
             "200": {
               "description": "Product list",
               "content": {
                 "application/json": {
                   "schema": {
                     "type": "array",
                     "items": {"$ref": "#/components/schemas/Product"}
                   }
                 }
               }
             }
           }
         }
       }
     },
     "components": {
       "schemas": {
         "Product": {
           "type": "object",
           "properties": {
             "id": {"type": "string"},
             "name": {"type": "string"},
             "price": {"type": "number"},
             "category": {"type": "string"}
           }
         }
       }
     }
   }
   ```
   
   Artifact ID: `art_j1k2l3m4n5o6`
```

---

## 🎯 Patterns Avanzati

### Pattern 1: Progressive Refinement

```
👤 User: Crea un sito web

🤖 Jarvis: Per cosa ti serve? Portfolio, e-commerce, blog, landing page...?

👤 User: Portfolio per sviluppatore

🤖 Jarvis: Vuoi qualcosa di minimale o con animazioni?
   Tech stack: HTML/CSS puro, React, Vue, Next.js...?

👤 User: Minimale, HTML/CSS

🤖 Jarvis: [Creates artifact: portfolio_base.html]
   
   Ecco la struttura base. Sezioni incluse:
   • Hero con nome e tagline
   • About me
   • Skills (con progress bars)
   • Projects gallery
   • Contact form
   
   Vuoi che aggiunga dark mode toggle?
```

---

### Pattern 2: Context Switching

```
👤 User: Sto lavorando su un progetto Python

🤖 Jarvis: [Salva contesto: progetto Python attivo]
   OK, dimmi di più. Che tipo di progetto?

👤 User: Un bot Telegram

🤖 Jarvis: [Update: bot Telegram in Python]
   Ottimo! Stai usando python-telegram-bot o aiogram?

[... dopo 1 ora, nuova sessione ...]

👤 User: Riprendiamo

🤖 Jarvis: [Recall: bot Telegram Python]
   Certo! Stavamo parlando del tuo bot Telegram in Python.
   Dove eravamo rimasti?
```

---

### Pattern 3: Error Recovery

```
👤 User: Quanto costa dogecoin?

🤖 Jarvis: [Tool: price_lookup("DOGE")]
   ❌ API timeout
   
   [Retry 1/2]
   ❌ API error
   
   [Fallback: web_search("dogecoin price")]
   ✅ Found price from CoinGecko
   
   DOGE è a circa $0.08 (dato da web search, non real-time API).
   ⚠️ Il servizio prezzi è temporaneamente lento.
```

---

## ✅ Best Practices

### 1. Conversazioni Strutturate

```
❌ BAD: "fammi vedere come si fa quella cosa"

✅ GOOD: "Mostrami come implementare autenticazione JWT in FastAPI"
```

### 2. Contesto Esplicito

```
❌ BAD: "aggiungi i test"

✅ GOOD: "Aggiungi test pytest per l'API FastAPI che abbiamo creato prima"
```

### 3. Feedback per Miglioramento

```
❌ BAD: "non funziona"

✅ GOOD: "Il codice dà questo errore: TypeError: 'str' object is not callable"
```

### 4. Sfrutta la Memoria

```
✅ "Come abbiamo discusso prima..."
✅ "Ricordi la funzione di sorting?"
✅ "Continua con lo stesso stile"
```

### 5. Usa i Comandi Avanzati

```
/think <query>      # Vedere il ragionamento
/context            # Verificare lo stato sessione
/artifacts          # Gestire i contenuti salvati
/reset              # Ricominciare da zero
```

---

## ❌ Anti-Patterns

### 1. Troppe Query Sconnesse

```
❌ 
"Meteo Roma"
"Scrivi codice Python"
"Prezzo BTC"
"Qual è la capitale della Francia"
"Debug questo errore"

→ La memoria si frammenta, perde coerenza
```

### 2. Query Troppo Vaghe

```
❌ "Aiutami"
❌ "Cosa devo fare?"
❌ "Dimmi qualcosa"

→ Tool selection confusa, risposte generiche
```

### 3. Ignorare il Contesto

```
❌ Ripetere sempre tutto il contesto
✅ "Come prima, ma con X diverso"
```

### 4. Session Infinite

```
❌ Non fare mai /reset
→ Context troppo lungo, summarization eccessiva

✅ /reset quando cambi progetto completamente
```

### 5. Aspettarsi Persistenza Eterna

```
❌ Aspettarsi che ricordi conversazioni di 2 mesi fa
→ TTL è 7 giorni

✅ Per info permanenti, salva in ChromaDB via /memory/fact
```

---

## 📊 Performance Tips

1. **Parallel Queries**: Le query multi-tool beneficiano da parallelizzazione
2. **Sliding Window**: Mantieni conversazioni focused per migliore contesto
3. **Artifacts**: Salva codice lungo come artifact invece di re-generare
4. **Summarization**: Lascia che il sistema auto-riassuma dopo 20 turni

---

## 🚀 Quick Reference

| Vuoi... | Comando/Azione |
|---------|----------------|
| Vedere il pensiero | `/think <query>` |
| Stato sessione | `/context` |
| Lista artifacts | `/artifacts` |
| Vedere artifact | `/artifact <id>` |
| Reset memoria | `/reset` |
| Ricerca web | `/web <query>` |
| Leggere URL | `/read <url>` |

---

**QuantumDev Max - Make the most of it!** 🚀
