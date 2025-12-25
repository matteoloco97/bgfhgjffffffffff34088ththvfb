# Telegram Bot Autoweb Integration

## Overview

Il Telegram bot integra **SmartIntentClassifier** per attivare automaticamente la ricerca web quando necessario, mantenendo backward compatibility al 100% con i comandi manuali esistenti.

## Come funziona

### Flusso automatico

Quando un utente invia un messaggio normale (non un comando), il bot:

1. **Classifica l'intent** usando SmartIntentClassifier
2. **Routing automatico** basato sull'intent rilevato:
   - `WEB_SEARCH` → Ricerca web automatica
   - `WEB_READ` → Lettura e riassunto pagina automatico
   - `DIRECT_LLM` → Chat normale con LLM

### Intent Detection

Il classificatore analizza il messaggio e rileva:

- **Weather queries**: "Meteo Roma?", "Che tempo fa?"
- **Price queries**: "Prezzo Bitcoin?", "Quanto vale Ethereum?"
- **Sports queries**: "Risultato Milan", "Classifica Serie A"
- **News queries**: "Ultime notizie", "Breaking news"
- **URL queries**: Qualsiasi messaggio con un URL
- **Code requests**: "Scrivi codice Python", "Genera script"
- **General chat**: "Ciao come stai?", "Dimmi una barzelletta"

### Routing Logic

```python
if intent == "WEB_READ" and url:
    # Leggi e riassumi la pagina
    final = await call_web_read(url, http, chat_id)
    
elif intent == "WEB_SEARCH":
    # Usa percorso veloce per live queries
    if live_type in ("weather", "price", "sports", "schedule", "news"):
        final = await call_web_summary_query(text, http, chat_id)
    else:
        # Ricerca avanzata per query complesse
        final = await call_web_research(text, http, chat_id)
    
else:  # DIRECT_LLM
    # Chat normale con LLM
    data = await call_chat(text, http, chat_id)
```

## Esempi di utilizzo

### Autoweb automatico

```
User: Meteo Roma?
Bot: 🌐 Autoweb WEB_SEARCH (live_type=weather)
     [Risultati meteo da web]

User: https://example.com
Bot: 🌐 Autoweb WEB_READ
     [Riassunto della pagina]

User: Prezzo Bitcoin?
Bot: 🌐 Autoweb WEB_SEARCH (live_type=price)
     [Quotazione Bitcoin in tempo reale]

User: Ciao come stai?
Bot: 💬 Direct LLM
     [Risposta conversazionale]
```

### Comandi manuali (backward compatible)

I comandi esistenti continuano a funzionare esattamente come prima:

```
/web Meteo Roma          → Forza ricerca web
/read https://example.com → Forza lettura pagina
/help                     → Mostra comandi disponibili
/status                   → Stato del sistema
```

## Logging e Debug

Il bot logga ogni intent rilevato per facilitare il debug:

```
📊 Intent detected: WEB_SEARCH (confidence=0.95, reason=weather_query, live_type=weather)
🌐 Autoweb WEB_SEARCH: Meteo Roma? (live_type=weather)
```

## Gestione Errori

Se l'autoweb fallisce per qualsiasi motivo, il bot fa automaticamente fallback a `/chat`:

```python
except Exception as e:
    log.warning(f"⚠️ Autoweb WEB_SEARCH failed: {e}, fallback to /chat")
    # Prosegue con call_chat normale
```

Questo garantisce che il bot continui sempre a funzionare anche in caso di errori.

## Configurazione

### Environment Variables

Nessuna configurazione aggiuntiva richiesta. Il bot rileva automaticamente se SmartIntentClassifier è disponibile:

```python
try:
    from core.smart_intent_classifier import SmartIntentClassifier
    _smart_intent = SmartIntentClassifier()
    log.info("✅ SmartIntentClassifier loaded for autoweb")
except Exception as e:
    _smart_intent = None
    log.warning(f"⚠️ SmartIntentClassifier not available: {e}")
```

### Verifica Status

L'utente può verificare lo status dell'autoweb con il comando `/start`:

```
🧠 Jarvis – AI personale di Matteo (QuantumDev)

🤖 Autoweb ATTIVO

• 💬 Chatta normalmente per usare Jarvis su qualsiasi tema
• 🌐 Autoweb intelligente: query su meteo, prezzi, sport, news vengono elaborate automaticamente
• 🔗 Invia un URL per ottenere automaticamente un riassunto
...
```

## Testing

### Unit Tests

Esegui i test completi:

```bash
python3 tests/test_telegram_autoweb.py
```

Test inclusi:
- ✅ Intent classification per tutti i casi d'uso
- ✅ Routing logic verification
- ✅ Backward compatibility check

### Manual Testing

Test manuali consigliati:

1. **Weather**: "Meteo Roma?" → Verifica ricerca web automatica
2. **Price**: "Prezzo Bitcoin?" → Verifica quotazione in tempo reale
3. **URL**: "https://news.ycombinator.com" → Verifica riassunto automatico
4. **Chat**: "Ciao come stai?" → Verifica chat normale
5. **Manual /web**: "/web Meteo Roma" → Verifica comando manuale
6. **Manual /read**: "/read https://example.com" → Verifica comando manuale

## Architettura

```
User Message
    ↓
handle_message()
    ↓
SmartIntentClassifier.classify()
    ↓
    ├─→ WEB_READ + url → call_web_read()
    ├─→ WEB_SEARCH (live) → call_web_summary_query()
    ├─→ WEB_SEARCH (complex) → call_web_research()
    └─→ DIRECT_LLM → call_chat()
```

## Backward Compatibility

✅ **100% backward compatible**

- Tutti i comandi esistenti funzionano esattamente come prima
- `/web` e `/read` hanno handler dedicati non influenzati dall'autoweb
- Nessun breaking change per gli utenti esistenti
- L'autoweb è completamente trasparente per l'utente

## Performance

- **Latenza aggiuntiva**: ~10-50ms per la classificazione intent
- **Cache**: Il classificatore usa pattern matching veloce (no LLM)
- **Fallback**: Se la classificazione fallisce, procede comunque con `/chat`

## Troubleshooting

### Autoweb non funziona

1. Verifica che SmartIntentClassifier sia disponibile:
   ```bash
   python3 -c "from core.smart_intent_classifier import SmartIntentClassifier; print('OK')"
   ```

2. Controlla i log del bot:
   ```bash
   tail -f telegram-bot.log | grep "Intent detected"
   ```

3. Verifica status con `/start` nel bot

### Intent sbagliato

Se il classificatore rileva un intent errato:

1. Controlla i log per vedere la confidence e il reason
2. Usa il comando manuale `/web` o `/read` per forzare il comportamento
3. Segnala il caso per migliorare il classificatore

### Fallback a /chat troppo frequente

Se l'autoweb fallisce spesso con fallback a `/chat`:

1. Verifica che i backend web siano disponibili:
   - `QUANTUM_WEB_SEARCH_URL`
   - `QUANTUM_WEB_SUMMARY_URL`
   - `QUANTUM_WEB_RESEARCH_URL`

2. Controlla i log per errori specifici

3. Testa i backend manualmente:
   ```bash
   curl -X POST http://127.0.0.1:8081/web/search -H "Content-Type: application/json" -d '{"q":"test"}'
   ```

## Future Enhancements

Possibili miglioramenti futuri:

- [ ] Aggiungere metriche per monitorare accuracy della classificazione
- [ ] Implementare feedback loop per migliorare il classificatore
- [ ] Aggiungere personalizzazione per utente (preferenze autoweb)
- [ ] Espandere live_type per nuove categorie (viaggi, ricette, etc.)
- [ ] Integrazione con analytics per tracking intent trends

## References

- `scripts/telegram_bot.py` - Implementazione principale
- `core/smart_intent_classifier.py` - Classificatore intent
- `tests/test_telegram_autoweb.py` - Test suite completi
