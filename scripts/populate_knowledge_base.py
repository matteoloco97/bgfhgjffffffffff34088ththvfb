#!/usr/bin/env python3
"""
scripts/populate_knowledge_base.py

Popola ChromaDB con knowledge interna su:
- Jarvis personale (AI generale)
- Infrastruttura hardware (CPU, GPU, tunnel)
- Architettura QuantumDev / Edge AI
"""

from utils.chroma_handler import add_fact


def _insert_group(group_name: str, facts: list[dict]) -> int:
    """
    Inserisce una lista di facts in Chroma usando add_fact(subject, value, source).
    - group_name viene usato come 'source' logico del fact.
    - NON passiamo liste (tags) per evitare problemi con i metadata.
    """
    inserted = 0
    for f in facts:
        subject = f["subject"].strip()
        value = f["value"].strip()
        source = f.get("source") or f"kb::{group_name}"
        # add_fact(subject, value, source)
        add_fact(subject, value, source)
        inserted += 1
    return inserted


def main() -> None:
    total = 0

    # =========================
    # 1) JARVIS: RUOLO & VISION
    # =========================
    jarvis_core = [
        {
            "subject": "jarvis_role",
            "value": (
                "Jarvis è l'AI personale generale di Matteo, prioritaria rispetto a tutte le verticali "
                "(betting, trading, casino, ecc.). Deve saper rispondere su qualsiasi tema e fungere da "
                "assistente centrale per ragionamento, pianificazione e decisioni."
            ),
        },
        {
            "subject": "jarvis_vertical_packs",
            "value": (
                "Le verticali (betting, trading, casino, tennis simulator, ecc.) vengono agganciate a Jarvis "
                "come 'pack' separati. Il core rimane generalista; le competenze verticali sono moduli "
                "attivabili sopra la stessa infrastruttura."
            ),
        },
        {
            "subject": "jarvis_personal_priority",
            "value": (
                "La priorità permanente del progetto è costruire Jarvis personale generalista prima di qualsiasi "
                "verticale, con memoria, strumenti personali e capacità di orchestrare agenti e modelli esterni."
            ),
        },
        {
            "subject": "jarvis_tone_and_style",
            "value": (
                "Jarvis deve avere uno stile diretto, analitico e onesto, capace di mettere in discussione le "
                "scelte dell'utente, evidenziare punti ciechi e costi di opportunità, invece di limitarsi a "
                "risposte accomodanti."
            ),
        },
        {
            "subject": "jarvis_tools_scope",
            "value": (
                "Jarvis deve integrare strumenti esterni come: web search, esecuzione codice, calendari, promemoria, "
                "email/file e altri tool personali, per agire come hub centrale dell'ecosistema digitale di Matteo."
            ),
        },
    ]
    total += _insert_group("jarvis_core", jarvis_core)

    # =========================
    # 2) HARDWARE & INFRA: CPU NODE
    # =========================
    infra_cpu = [
        {
            "subject": "cpu_node_contabo",
            "value": (
                "Il nodo CPU principale per Jarvis e QuantumDev è una VPS Contabo Cloud VPS 20 con 6 vCPU, "
                "12 GB di RAM, 100 GB di storage NVMe e sistema operativo Ubuntu 22.04. "
                "Su questo nodo girano FastAPI (quantum-api), Redis, ChromaDB, il bot Telegram e la logica di routing."
            ),
        },
        {
            "subject": "cpu_node_services",
            "value": (
                "Sul nodo CPU vengono eseguiti: quantum-api (FastAPI/Uvicorn), Redis per cache, ChromaDB per memoria "
                "a lungo termine, orchestratore web/search, integrazione con browserless e il bot Telegram "
                "che espone Jarvis all'utente."
            ),
        },
    ]
    total += _insert_group("infra_cpu", infra_cpu)

    # =========================
    # 3) HARDWARE & INFRA: GPU NODE
    # =========================
    infra_gpu = [
        {
            "subject": "gpu_node_main_model",
            "value": (
                "Il modello principale è Qwen 2.5 32B AWQ servito tramite vLLM su un server GPU remoto con 48 GB di VRAM. "
                "L'endpoint è esposto come API compatibile OpenAI sulla porta 9011, con path /v1/chat/completions e /v1/models."
            ),
        },
        {
            "subject": "gpu_node_context_and_tokens",
            "value": (
                "Il server vLLM per Qwen 2.5 32B AWQ è configurato con max context 4096 token per bilanciare qualità e "
                "latenza. L'API lato CPU usa LLM_MAX_TOKENS ≈ 384 per tenere le risposte compatte e veloci."
            ),
        },
        {
            "subject": "gpu_cpu_tunnel",
            "value": (
                "La comunicazione tra CPU Contabo e GPU remota avviene tramite tunnel SSH inverso sulla porta 9011. "
                "Il nodo GPU ascolta localmente e il tunnel espone il servizio sul nodo CPU come 127.0.0.1:9011."
            ),
        },
        {
            "subject": "gpu_usage_profile",
            "value": (
                "Il modello Qwen 2.5 32B AWQ sfrutta quasi tutta la VRAM disponibile (circa 48 GB) per le KV cache "
                "e il context; la configurazione è ottimizzata per ridurre la latenza delle risposte singole, "
                "privilegiando qualità di reasoning su throughput multiutente."
            ),
        },
    ]
    total += _insert_group("infra_gpu", infra_gpu)

    # =========================
    # 4) MEMORY ARCH: CHROMA + REDIS
    # =========================
    memory_arch = [
        {
            "subject": "memory_chroma_collections",
            "value": (
                "ChromaDB è usato come memoria a lungo termine con almeno tre collezioni principali: "
                "'facts' per knowledge generale e note strutturate, 'prefs' per preferenze e stile utente, "
                "e 'betting_history' per lo storico dell'operatività sul betting."
            ),
        },
        {
            "subject": "memory_embeddings_model",
            "value": (
                "Per ChromaDB viene usato il modello di embedding 'sentence-transformers/all-MiniLM-L6-v2', "
                "che bilancia velocità e qualità, adatto per recuperare contesto e fatti in modo rapido."
            ),
        },
        {
            "subject": "memory_redis_cache",
            "value": (
                "Redis è usato come livello di cache per risposte LLM, cache semantica e mirror di alcune parti "
                "della memoria. Questo riduce la latenza sulle richieste ripetute e aiuta a scalare l'accesso ai dati."
            ),
        },
        {
            "subject": "memory_semantic_cache_goal",
            "value": (
                "L'obiettivo della semantic cache è riutilizzare risposte a domande molto simili, evitando di "
                "rifare chiamate complete alla LLM quando l'edge informativo non cambia in modo rilevante."
            ),
        },
    ]
    total += _insert_group("memory_arch", memory_arch)

    # =========================
    # 5) QUANTUM / EDGE AI VISION
    # =========================
    quantum_edge = [
        {
            "subject": "quantum_storage_central",
            "value": (
                "Wasabi S3 (bucket 'quantum-memory', regione eu-central-2) è lo storage centrale permanente "
                "per backup, dataset e knowledge dell'ecosistema Quantum. Le GPU sono il motore cognitivo "
                "temporaneo, mentre Wasabi è la memoria storica persistente."
            ),
        },
        {
            "subject": "quantum_edge_ai_vision",
            "value": (
                "Quantum Edge AI è la fase futura in cui l'intelligenza viene distribuita: modelli più leggeri "
                "girano vicino alle fonti dati (browser, VPS secondarie, dispositivi), mentre i modelli pesanti "
                "restano su GPU dedicate, orchestrati da Jarvis come cervello centrale."
            ),
        },
        {
            "subject": "quantum_agents_architecture",
            "value": (
                "L'architettura prevede agenti modulari: Telegram Bot, Flush Cache, Backup, Restore, "
                "Monitor, Orchestrator, ChromaBridge, API Gateway. Gli agenti comunicano tramite FastAPI, Redis "
                "e Wasabi, coordinati dalla logica centrale di Jarvis/QuantumDev."
            ),
        },
        {
            "subject": "quantum_scalability_goal",
            "value": (
                "Fin dall'inizio il sistema Quantum è progettato per essere scalabile a decine di migliaia di utenti "
                "al mese, usando GPU moderne per l'inferenza, storage S3-compatibile per i dati e servizi stateless "
                "sulla parte CPU."
            ),
        },
    ]
    total += _insert_group("quantum_edge", quantum_edge)

    # =========================
    # 6) ROUTING & KNOWLEDGE LAYERS
    # =========================
    routing = [
        {
            "subject": "routing_knowledge_layers",
            "value": (
                "Jarvis combina tre fonti principali di conoscenza: knowledge nativa del modello (LLM), "
                "memoria strutturata in ChromaDB e web search multi-provider per dati live e post-cutoff. "
                "Uno smart router decide quando usare solo la LLM e quando integrare memoria o web."
            ),
        },
        {
            "subject": "routing_preference_default_llm",
            "value": (
                "Per tutte le query concettuali, storiche, di coding o reasoning generale, il sistema preferisce "
                "usare solo la LLM senza web, perché è più veloce e abbastanza accurata nella maggior parte dei casi."
            ),
        },
        {
            "subject": "routing_when_web_needed",
            "value": (
                "Il web viene usato principalmente per: meteo, prezzi, risultati sportivi, news recenti, contenuti "
                "specifici da URL e tutto ciò che è oltre il knowledge cutoff o richiede dati in tempo reale."
            ),
        },
    ]
    total += _insert_group("routing_arch", routing)

    print(f"✅ Popolazione knowledge base completata. Facts inseriti: {total}")


if __name__ == "__main__":
    main()
