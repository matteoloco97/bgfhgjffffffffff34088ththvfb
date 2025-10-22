#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bootstrap/Setup Mixtral-8x7B (vLLM) su GPU
- Installa dipendenze
- Chiude istanze vLLM precedenti
- Avvia server OpenAI-compatibile su porta configurabile
- Attende readiness con timeout configurabile
- Testa il modello
- Registra l'endpoint sul backend QuantumDev

Ambientabili:
  VLLM_PORT            : default 8001
  MODEL_NAME           : default mistralai/Mixtral-8x7B-Instruct-v0.1
  MODEL_ALIAS          : default mixtral-8x7b
  WAIT_TIMEOUT         : default 3600 (sec, 60 min)
  QUANTUM_BACKEND_API  : default http://84.247.166.247:8081/update_gpu
  QUANTUM_SHARED_SECRET: HMAC key per registrazione backend
"""

import os
import time
import shutil
import subprocess
import hmac
import hashlib
import json
from pathlib import Path

# ================== CONFIG ==================
MODEL_NAME = os.environ.get("MODEL_NAME", "mistralai/Mixtral-8x7B-Instruct-v0.1")
MODEL_ALIAS = os.environ.get("MODEL_ALIAS", "mixtral-8x7b")
VLLM_PORT = int(os.environ.get("VLLM_PORT", "8001"))
WAIT_TIMEOUT = int(os.environ.get("WAIT_TIMEOUT", "3600"))  # 60 min default

# Backend VPS
QUANTUM_BACKEND_API = os.environ.get(
    "QUANTUM_BACKEND_API",
    "http://84.247.166.247:8081/update_gpu"
)
QUANTUM_SHARED_SECRET = os.environ.get(
    "QUANTUM_SHARED_SECRET",
    "5e6ad9f7c2b14dceb2f4a1a9087c3da0d4a885c3e85f1b2d47a6f0e9c3b21d77"
)

LOG_PATH = Path.home() / "vllm_mixtral.log"

print("🧠 QuantumDev GPU - Mixtral-8x7B Bootstrap")
print("=" * 60)

# ------------------ Helpers ------------------
def run(cmd, *, env=None, check=True):
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, env=env, check=check)

def pip_install():
    os.environ["PIP_ROOT_USER_ACTION"] = "ignore"
    run(["python3", "-m", "pip", "install", "-U", "pip"])
    # vLLM versione stabile + requests per health check/registrazione
    run(["python3", "-m", "pip", "install", "-U", "vllm==0.6.3.post1", "requests"])
    print("✅ vLLM installato/aggiornato")

def kill_old_vllm():
    """Ferma vecchie istanze vLLM e libera la porta."""
    print("🔪 Fermo vecchie istanze vLLM…")
    subprocess.run(["pkill", "-9", "-f", "vllm.entrypoints"], check=False)
    time.sleep(2)

    # Kill anche su porta specifica
    if shutil.which("lsof"):
        try:
            out = subprocess.check_output(
                ["lsof", "-t", "-i", f"tcp:{VLLM_PORT}"],
                text=True
            ).strip()
            if out:
                for pid in {p for p in out.splitlines() if p.strip()}:
                    print(f"   Killing PID {pid} on port {VLLM_PORT}")
                    subprocess.run(["kill", "-9", pid], check=False)
        except subprocess.CalledProcessError:
            pass
    print("✅ Vecchie istanze fermate")

def start_vllm_mixtral():
    """Avvia vLLM con Mixtral (RTX 3090 24GB friendly)."""
    print("\n🚀 Avvio Mixtral-8x7B…")
    print(f"   Model : {MODEL_NAME}")
    print(f"   Port  : {VLLM_PORT}")
    print(f"   Ctx   : 32K tokens")
    print(f"   Log   : {LOG_PATH}")

    # Set/Unset env che a volte creano problemi
    os.environ.pop("PYTORCH_CUDA_ALLOC_CONF", None)
    os.environ["VLLM_USE_FLASH_ATTN"] = "0"  # disattiva FlashAttn se instabile su 3090

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    logf = open(LOG_PATH, "ab", buffering=0)

    cmd = [
        "python3", "-m", "vllm.entrypoints.openai.api_server",
        "--model", MODEL_NAME,
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--dtype", "float16",
        "--max-model-len", "32768",   # 32K context
        "--tensor-parallel-size", "1",  # single GPU (vLLM splitter locale)
        "--gpu-memory-utilization", "0.95",
        "--max-num-seqs", "32",       # batch dinamico
    ]

    print(f"\n🔧 Comando: {' '.join(cmd)}\n")

    return subprocess.Popen(
        cmd,
        stdout=logf,
        stderr=subprocess.STDOUT,
        start_new_session=True
    )

def wait_ready(timeout=WAIT_TIMEOUT):
    """Attende che l'API /v1/models risponda entro 'timeout' secondi."""
    import requests
    url = f"http://127.0.0.1:{VLLM_PORT}/v1/models"

    print(f"\n⏳ Attendo vLLM (timeout: {timeout}s)…")
    print("   Il primo download (≈47 GB) può richiedere 30–60 min in media.")

    t0 = time.time()
    spinner = "|/-\\"
    i = 0

    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                data = r.json()
                models = [m['id'] for m in data.get('data', [])]
                print(f"\n✅ vLLM pronto!")
                print(f"   Modelli disponibili: {models}")
                return True
        except Exception:
            pass

        print(f"\r   {spinner[i % len(spinner)]} ", end="", flush=True)
        i += 1
        time.sleep(2)

    print(f"\n⚠️  vLLM non ancora pronto dopo {timeout}s")
    print(f"   Controlla log: tail -f {LOG_PATH}")
    return False

def get_public_ip():
    import requests
    try:
        return requests.get("http://checkip.amazonaws.com", timeout=5).text.strip()
    except Exception:
        return "127.0.0.1"

def sign_payload(payload: dict) -> str:
    """Genera firma HMAC per autenticazione con il backend."""
    payload_str = json.dumps(payload, separators=(',', ':'))
    return hmac.new(
        QUANTUM_SHARED_SECRET.encode(),
        payload_str.encode(),
        hashlib.sha256
    ).hexdigest()

def register_backend(ip: str):
    """Registra endpoint Mixtral su backend QuantumDev."""
    import requests

    payload = {
        "llm_endpoint": f"http://{ip}:{VLLM_PORT}/v1/chat/completions",
        "model": MODEL_ALIAS
    }

    signature = sign_payload(payload)
    headers = {
        "Content-Type": "application/json",
        "X-GPU-Signature": signature
    }

    print("\n🔗 Registro Mixtral su QuantumDev…")
    print(f"   Endpoint: {payload['llm_endpoint']}")
    print(f"   Model   : {payload['model']}")

    try:
        r = requests.post(
            QUANTUM_BACKEND_API,
            json=payload,
            headers=headers,
            timeout=30
        )
        if r.ok:
            print(f"✅ Registrato: {r.json()}")
        else:
            print(f"⚠️  Backend {r.status_code}: {r.text[:300]}")
    except Exception as e:
        print(f"❌ Errore registrazione: {e}")

def test_mixtral():
    """Test rapido chat completions."""
    import requests

    print("\n🧪 Test Mixtral…")

    payload = {
        "model": MODEL_ALIAS,   # alias lato backend, qui è solo indicativo
        "messages": [
            {"role": "system", "content": "Sei un assistente conciso."},
            {"role": "user", "content": "Dimmi solo: quanto fa 7x8? (rispondi con un numero)"},
        ],
        "temperature": 0.2,
        "max_tokens": 16
    }

    try:
        r = requests.post(
            f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions",
            json=payload,
            timeout=60
        )
        if r.ok:
            data = r.json()
            answer = data["choices"][0]["message"]["content"].strip()
            print(f"✅ Mixtral risponde: '{answer}'")
            return True
        else:
            print(f"❌ Test fallito: HTTP {r.status_code} – {r.text[:200]}")
            return False
    except Exception as e:
        print(f"❌ Test error: {e}")
        return False

# ================== MAIN ==================
def main():
    import argparse
    ap = argparse.ArgumentParser(description="Bootstrap Mixtral vLLM")
    ap.add_argument("action", nargs="?", default="setup-run",
                    choices=["setup", "run", "setup-run"],
                    help="setup=install deps; run=avvia server; setup-run=tutto")
    args = ap.parse_args()

    if args.action in ("setup", "setup-run"):
        print("\n📦 STEP 1: Installazione dipendenze")
        pip_install()

        print("\n🛑 STEP 2: Fermo vecchie istanze")
        kill_old_vllm()

    if args.action in ("run", "setup-run"):
        print("\n🚀 STEP 3: Avvio Mixtral-8x7B")
        proc = start_vllm_mixtral()
        print(f"   PID: {proc.pid}")

        print("\n⏳ STEP 4: Attendo download + init")
        ready = wait_ready(timeout=WAIT_TIMEOUT)

        if not ready:
            print("\n❌ Setup/Run non completato nei tempi. Log:")
            print(f"   tail -50 {LOG_PATH}")
            return 1

        print("\n🧪 STEP 5: Test funzionalità")
        if not test_mixtral():
            print("⚠️  Test fallito, ma vLLM è avviato; verifica i log.")

        print("\n🌐 STEP 6: Ottieni IP pubblico")
        ip = get_public_ip()
        print(f"   IP: {ip}")

        print("\n🔗 STEP 7: Registra su backend")
        register_backend(ip)

        print("\n" + "=" * 60)
        print("✅ SETUP COMPLETATO!")
        print("=" * 60)
        print(f"\n📊 Info:")
        print(f"   - Modello : {MODEL_NAME}")
        print(f"   - Alias   : {MODEL_ALIAS}")
        print(f"   - Context : 32K tokens")
        print(f"   - Endpoint: http://{ip}:{VLLM_PORT}")
        print(f"   - Log     : {LOG_PATH}")
        print(f"\n📝 Log live: tail -f {LOG_PATH}")
        print(f"🔄 Restart : pkill -f vllm && ./bootstrap_mixtral.py run")
    return 0

if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n\n⚠️  Interrotto dall'utente")
        raise SystemExit(1)
