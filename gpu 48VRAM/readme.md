Markdown

# 🚀 GPU Inference Node (Vast.ai) - "The Muscles"

Questa cartella contiene la configurazione per il nodo di inferenza AI che gira su server GPU (Vast.ai).
Il sistema agisce come backend di calcolo puro, esponendo API OpenAI-compatible che vengono consumate dal server centrale (VPS Contabo) tramite un tunnel SSH sicuro.

## 🏗 Architettura

* **Modello:** `DeepSeek-R1-Distill-Qwen-32B-abliterated-Q6_K.gguf`
* **Engine:** Text Generation WebUI (Oobabooga) + `llama.cpp` loader
* **Hardware Target:** NVIDIA RTX A6000 / A40 (o superiore con >24GB VRAM)
* **Connessione:** API esposte su porta `5000`, accessibili SOLO via Tunnel SSH (no public internet exposure).

---

## 🛠 Setup & Ripristino (Quick Start)

Se l'istanza viene distrutta o riavviata, segui questi passaggi per tornare online in 2 minuti.

### 1. Avvio del Server AI (Persistente)
Per garantire che il server si riavvii automaticamente in caso di crash o errori di memoria, usiamo uno script di loop all'interno di `tmux`.

1.  Accedi al terminale di Vast.ai.
2.  Crea/Entra nella sessione tmux:
    ```bash
    tmux new -s cervello
    ```
3.  Lancia il **Loop di Avvio** (Copia-Incolla tutto il blocco):
    ```bash
    cd /workspace/text-generation-webui/
    
    while true; do
        echo "🧠 [$(date)] Avvio del Cervello AI..."
        
        ./start_linux.sh --listen --api --api-port 5000 \
        --model DeepSeek-R1-Distill-Qwen-32B-abliterated-Q6_K.gguf \
        --loader llama.cpp \
        --n-gpu-layers 100 \
        --n_ctx 32768
        
        echo "⚠️ [$(date)] AI CRASHATA! Riavvio automatico tra 5 secondi..."
        sleep 5
    done
    ```
4.  **Detach** (Lascia girare in background):
    * Premi `CTRL` + `B`, rilascia, poi premi `D`.
    * *Oppure chiudi semplicemente la finestra del terminale.*

### 2. Verifica Stato
Per controllare se l'AI sta girando o per leggere i log:
```bash
tmux attach -t cervello

🔗 Collegamento con il "Cervello" (Contabo VPS)

La GPU non è esposta su internet pubblico. Per collegarla alla VPS che esegue la logica applicativa, usiamo un Reverse Tunnel SSH Persistente lato VPS.

Dati necessari da Vast.ai:

    IP_HOST: L'indirizzo IP pubblico dell'istanza.

    PORT_SSH: La porta assegnata per SSH (es. 31542).

Comando (da eseguire sulla VPS Contabo):
Bash

# Sostituisci con i dati attuali dell'istanza Vast
ssh -o ServerAliveInterval=60 -N -L 5000:localhost:5000 root@IP_HOST -p PORT_SSH

Vedi il README nella cartella server/ o vps/ per lo script di auto-reconnection del tunnel.
📂 Gestione Modelli

I modelli GGUF devono essere posizionati in: /workspace/text-generation-webui/user_data/models/

Comando per scaricare nuovi modelli (esempio):
Bash

cd /workspace/text-generation-webui/
python download-model.py --output user_data/models/ TheBloke/Nome-Modello-GGUF

📝 Note Tecniche

    Context Window: Impostata a 32768 token. Se si verificano errori OOM (Out Of Memory), ridurre questo valore nel comando di avvio.

    Porta API: 5000 (OpenAI Compatible). La porta WebUI 7860 è attiva ma non utilizzata per la produzione.
