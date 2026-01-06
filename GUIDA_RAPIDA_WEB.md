# 🚀 Guida Rapida - Interfaccia Web QuantumDev AI

## Avvio in 3 Passi

### 1. Installa Dipendenze (se non già fatto)

```bash
cd /home/runner/work/bgfhgjffffffffff34088ththvfb/bgfhgjffffffffff34088ththvfb
pip install -r requirements.txt
```

### 2. Configura (Opzionale)

Il sistema funziona con configurazioni default, ma puoi personalizzare:

```bash
# Copia il file di esempio
cp .env.example .env

# Modifica .env con il tuo editor preferito
nano .env
```

**Variabili principali:**
```bash
# Endpoint LLM
LLM_ENDPOINT=http://127.0.0.1:5000/v1

# Auto Web Search (già abilitato)
AUTO_SEARCH_ENABLED=true

# Streaming (già abilitato)  
STREAMING_ENABLED=true
```

### 3. Avvia il Server

```bash
# Avvio standard
uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8000

# Oppure con auto-reload per sviluppo
uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8000 --reload
```

### 4. Apri il Browser

Vai su: **http://localhost:8000**

## ✨ Prime Cose da Provare

### 1. Chat Semplice

Scrivi: `Ciao, come funzioni?`

### 2. Auto Web Search

Scrivi: `Qual è il prezzo attuale di Bitcoin?`

Guarda l'indicatore di ricerca web attivarsi automaticamente!

### 3. Codice

Scrivi: `Scrivi uno script Python per ordinare una lista`

Vedi il syntax highlighting del codice!

### 4. Upload File

1. Click sull'icona graffetta
2. Seleziona un'immagine o PDF
3. Scrivi: `Analizza questo file`

### 5. Esporta Conversazione

1. Click sull'icona download nell'header
2. Scarica la conversazione in Markdown

### 6. Cambia Tema

Click sul pulsante luna/sole nella sidebar per dark/light mode

### 7. Impostazioni

1. Click su "Impostazioni"
2. Prova a cambiare la temperatura
3. Salva e vedi la differenza

## 🎯 Features Principali

| Feature | Descrizione | Come Usare |
|---------|-------------|------------|
| **Streaming** | Risposte in tempo reale | Automatico |
| **Auto Web** | Ricerca web automatica | Automatico quando necessario |
| **Files** | Upload immagini/PDF | Click graffetta |
| **History** | Storia conversazioni | Sidebar a sinistra |
| **Export** | Scarica chat | Icon download |
| **Settings** | Personalizza | Icon ingranaggio |
| **Dark Mode** | Tema scuro | Icon luna |

## 🔧 Risoluzione Problemi

### Server non parte

**Errore:** `ModuleNotFoundError: No module named 'fastapi'`

**Soluzione:**
```bash
pip install -r requirements.txt
```

### Interfaccia non carica

**Errore:** 404 Not Found

**Soluzione:**
Verifica che la directory frontend esista:
```bash
ls -la frontend/
# Dovresti vedere: templates/ e static/
```

### Streaming non funziona

**Problema:** Le risposte non appaiono progressivamente

**Soluzione:**
1. Verifica che `/chat/stream` endpoint esista
2. Controlla la console del browser per errori
3. Assicurati che `STREAMING_ENABLED=true` in .env

### Auto Web Search non si attiva

**Problema:** Le query non triggherano la ricerca web

**Soluzione:**
Verifica in .env:
```bash
AUTO_SEARCH_ENABLED=true
AUTO_SEARCH_CONFIDENCE_THRESHOLD=0.7
```

### Upload file fallisce

**Problema:** "Upload failed"

**Soluzione:**
1. Verifica dimensione file (max 10MB)
2. Controlla che il tipo di file sia supportato
3. Guarda i log del backend per dettagli

## 📱 Accesso da Altri Dispositivi

Per accedere da smartphone/tablet sulla stessa rete:

1. Trova il tuo IP locale:
   ```bash
   # Linux/Mac
   ifconfig | grep inet
   
   # Windows
   ipconfig
   ```

2. Usa quell'IP invece di localhost:
   ```
   http://192.168.1.X:8000
   ```

## 🌐 Deploy in Produzione

### Con Nginx (Raccomandato)

1. **Installa Nginx**
   ```bash
   sudo apt install nginx
   ```

2. **Configura Nginx** (`/etc/nginx/sites-available/quantumdev`)
   ```nginx
   server {
       listen 80;
       server_name your-domain.com;

       location / {
           proxy_pass http://127.0.0.1:8000;
           proxy_set_header Host $host;
           proxy_set_header X-Real-IP $remote_addr;
           proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       }

       location /static/ {
           alias /path/to/frontend/static/;
       }
   }
   ```

3. **Abilita e riavvia**
   ```bash
   sudo ln -s /etc/nginx/sites-available/quantumdev /etc/nginx/sites-enabled/
   sudo nginx -t
   sudo systemctl restart nginx
   ```

### Con Systemd Service

1. **Crea service file** (`/etc/systemd/system/quantumdev.service`)
   ```ini
   [Unit]
   Description=QuantumDev AI Service
   After=network.target

   [Service]
   Type=simple
   User=your-user
   WorkingDirectory=/path/to/quantumdev
   Environment="PATH=/path/to/venv/bin"
   ExecStart=/path/to/venv/bin/uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8000
   Restart=always

   [Install]
   WantedBy=multi-user.target
   ```

2. **Abilita e avvia**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl enable quantumdev
   sudo systemctl start quantumdev
   ```

### Con Docker (Se disponibile)

```bash
# Build
docker build -t quantumdev-ai .

# Run
docker run -d -p 8000:8000 \
  --name quantumdev \
  -v $(pwd)/.env:/app/.env \
  quantumdev-ai
```

## 🎨 Personalizzazione Rapida

### Cambia Titolo

Modifica `frontend/templates/chat.html`:
```html
<title>Il Mio AI Assistente</title>
```

### Cambia Colori

Modifica `frontend/static/css/chat.css`:
```css
:root {
    --primary-color: #your-color;
}
```

### Aggiungi Prompts di Esempio

Modifica `frontend/templates/chat.html`:
```html
<button class="example-prompt">Il tuo prompt personalizzato</button>
```

## 📊 Monitoring

### Logs

```bash
# Guarda i logs in tempo reale
tail -f logs/quantumdev.log
```

### Metriche

Accedi a: `http://localhost:8000/metrics`

Per vedere:
- Richieste totali
- Latenza media
- Errori
- Cache hit rate

### System Status

Accedi a: `http://localhost:8000/system/status`

## 🎓 Tips & Tricks

### 1. Keyboard Shortcuts

- `Enter` - Invia messaggio
- `Shift + Enter` - Nuova riga
- `Ctrl/Cmd + K` - Nuova chat (coming soon)

### 2. Markdown Supportato

```markdown
# Titolo
## Sottotitolo

**Bold** e *Italic*

- Lista
- Elementi

1. Lista
2. Numerata

`codice inline`

```python
# Blocco codice
print("Hello")
```

[Link](url)

> Quote
```

### 3. Comandi Speciali (se implementati)

- `/web query` - Forza ricerca web
- `/clear` - Cancella chat
- `/export` - Esporta conversazione

## 💡 Best Practices

1. **Usa Auto Web Search** - Lascia che il sistema decida quando cercare
2. **Salva conversazioni importanti** - Usa export regolarmente
3. **Regola temperatura** - 0.7 per bilanciato, 1.0+ per creatività
4. **Monitora token** - Imposta max_tokens appropriato per le tue risposte
5. **Verifica fonti** - Controlla sempre le citazioni web

## 🆘 Supporto

### Problemi Comuni

1. **Performance lenta**
   - Riduci max_tokens
   - Disabilita streaming temporaneamente
   - Pulisci cache browser

2. **Memoria piena**
   - Cancella conversazioni vecchie
   - Riduci CONVERSATION_MAX_HISTORY

3. **Errori di connessione**
   - Verifica che Redis sia attivo
   - Controlla LLM endpoint
   - Vedi logs per dettagli

### Dove Cercare Aiuto

1. **Logs del backend**
   ```bash
   tail -f logs/quantumdev.log
   ```

2. **Console del browser**
   - F12 → Console tab
   - Cerca errori in rosso

3. **System status**
   - http://localhost:8000/system/status

## 🚀 Next Level

Quando sei comodo con le basi, prova:

1. **Configura GPU monitoring** - Vedi dashboard GPU
2. **Abilita autonomous mode** - Lascia che l'AI esegua task complessi
3. **Integra Telegram bot** - Chat anche da mobile
4. **Setup knowledge graph** - Memoria semantica avanzata
5. **Deploy in produzione** - Rendi accessibile al mondo

## 🎉 Divertiti!

Hai ora un'AI personale potente e senza censura. Esplora, sperimenta e goditi la libertà!

**Buon coding! 🤖✨**
