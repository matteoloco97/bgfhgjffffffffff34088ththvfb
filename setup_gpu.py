#!/usr/bin/env python3
"""
setup_gpu.py - Setup automatico Qwen 32B AWQ su Vast.ai
Configurazione completa con vLLM, Telegram notifications e backend registration
"""

import hashlib
import hmac
import json
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path

# ========= CONFIGURAZIONE =========

WORKSPACE = Path("/workspace")
VENV_DIR = Path("/venv/qwen")
LOG_FILE = WORKSPACE / "setup_qwen.log"
LOG_PATH = WORKSPACE / "vllm_qwen.log"

MODEL_PATH = WORKSPACE / "models" / "qwen-32b-awq"
HF_CACHE = WORKSPACE / "hf_cache"

# Modello: Qwen 32B AWQ
MODEL_REPO = "Qwen/Qwen2.5-32B-Instruct-AWQ"
SERVED_MODEL_NAME = "qwen-32b-instruct"
VLLM_PORT = 9011

# Configurazione vLLM ottimizzata per A40 48GB
MAX_MODEL_LEN = 32768  # Context length: 32K tokens
GPU_MEMORY_UTIL = 0.85  # 85% GPU memory utilization
MAX_NUM_SEQS = 4  # Batch size ottimizzato

# Caricamento configurazione da variabili d'ambiente
CPU_HOST = os.getenv("CPU_HOST", "")
CPU_USER = os.getenv("CPU_USER", "root")
CPU_PORT = int(os.getenv("CPU_PORT", "22"))
CPU_TUNNEL_PORT = int(os.getenv("CPU_TUNNEL_PORT", "9011"))

GPU_SSH_PRIVATE_KEY = os.getenv("GPU_SSH_PRIVATE_KEY", "").strip()

BACKEND_API = os.getenv("BACKEND_API", "")
SHARED_SECRET = os.getenv("SHARED_SECRET", "").strip()

# Telegram notifications
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "").strip()

# Genera correlation ID per tracking
CORRELATION_ID = str(uuid.uuid4())[:8]

# ========= LOGGING =========


def log(msg: str, level="INFO"):
    """Log message con timestamp, correlation ID e livello."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{CORRELATION_ID}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        print(f"Warning: Could not write to log file: {e}", file=sys.stderr)


def section(title: str):
    """Crea una sezione visibile nei log."""
    log("=" * 80)
    log(title)
    log("=" * 80)


# ========= TELEGRAM NOTIFICATIONS =========


def send_telegram(message: str, parse_mode="HTML"):
    """Invia notifica Telegram all'admin."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        return False
    
    try:
        import requests
        
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        data = {
            "chat_id": TELEGRAM_ADMIN_ID,
            "text": message,
            "parse_mode": parse_mode
        }
        
        r = requests.post(url, json=data, timeout=10)
        return r.ok
    except Exception as e:
        log(f"⚠️  Telegram notification failed: {e}", "WARN")
        return False


def notify_start():
    """Notifica inizio setup."""
    msg = (
        f"🚀 <b>QuantumDev GPU Setup Started</b>\n\n"
        f"📋 Correlation ID: <code>{CORRELATION_ID}</code>\n"
        f"🤖 Model: Qwen2.5-32B-Instruct-AWQ\n"
        f"🔧 Config: 32K context, 85% VRAM\n"
        f"⏰ Started: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram(msg)


def notify_success(elapsed_sec: int):
    """Notifica completamento con successo."""
    msg = (
        f"✅ <b>GPU Setup Complete!</b>\n\n"
        f"📋 Correlation ID: <code>{CORRELATION_ID}</code>\n"
        f"⏱️ Time: {elapsed_sec//60}m {elapsed_sec%60}s\n"
        f"🌐 Endpoint: http://0.0.0.0:{VLLM_PORT}\n"
        f"🎉 Sistema operativo!"
    )
    send_telegram(msg)


def notify_error(error_msg: str):
    """Notifica errore durante setup."""
    msg = (
        f"❌ <b>GPU Setup Failed</b>\n\n"
        f"📋 Correlation ID: <code>{CORRELATION_ID}</code>\n"
        f"🔴 Error: {error_msg}\n"
        f"⏰ Time: {time.strftime('%Y-%m-%d %H:%M:%S')}"
    )
    send_telegram(msg)


# ========= ENVIRONMENT DETECTION =========


class Env:
    """Rileva e gestisce informazioni sull'ambiente GPU."""
    
    def __init__(self):
        self.cuda_version = self._cuda_version()
        self.cuda_major = int(self.cuda_version.split(".")[0]) if self.cuda_version else 12
        self.gpu_name = self._gpu_name()
        self.vram_gb = self._vram_gb()

    def _cuda_version(self) -> str:
        """Rileva versione CUDA installata."""
        try:
            r = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5)
            m = re.search(r"CUDA Version:\s+(\d+\.\d+)", r.stdout)
            if m:
                return m.group(1)
        except Exception:
            pass
        return "12.1"

    def _gpu_name(self) -> str:
        """Rileva nome GPU."""
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return r.stdout.strip()
        except Exception:
            return "Unknown"

    def _vram_gb(self) -> int:
        """Rileva VRAM disponibile in GB."""
        try:
            r = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return int(r.stdout.strip()) // 1024
        except Exception:
            return 48

    def summary(self):
        """Mostra summary dell'ambiente."""
        section("🔍 ENVIRONMENT DETECTION")
        log(f"GPU  : {self.gpu_name}")
        log(f"VRAM : {self.vram_gb} GB")
        log(f"CUDA : {self.cuda_version} (major: {self.cuda_major})")


def run(cmd, check=True, shell=False, timeout=None):
    """Esegue comando con error handling."""
    try:
        return subprocess.run(
            cmd, check=check, shell=shell, timeout=timeout, capture_output=False, text=True
        )
    except subprocess.CalledProcessError:
        if check:
            log(f"Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}", "ERROR")
            raise
        return None


# ========= VIRTUAL ENVIRONMENT =========


def ensure_venv() -> str:
    """Crea e configura virtual environment Python."""
    section("🐍 PYTHON VIRTUAL ENVIRONMENT")
    if not VENV_DIR.exists():
        VENV_DIR.mkdir(parents=True, exist_ok=True)
        run(["python3", "-m", "venv", str(VENV_DIR)])
    py = str(VENV_DIR / "bin" / "python")
    run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=False)
    log("✅ Virtual environment ready")
    return py


def install_deps(py: str, cuda_major: int):
    """Installa dipendenze Python necessarie."""
    section("📦 INSTALLING DEPENDENCIES")

    # Pacchetti base
    log("Installing base packages...")
    run(
        [
            py,
            "-m",
            "pip",
            "install",
            "-q",
            "-U",
            "huggingface-hub",
            "transformers",
            "requests",
            "jinja2",
        ],
        timeout=300,
    )

    # PyTorch 2.5.1
    log("Installing PyTorch 2.5.1...")
    idx = (
        "https://download.pytorch.org/whl/cu121"
        if cuda_major >= 12
        else "https://download.pytorch.org/whl/cu118"
    )
    run([py, "-m", "pip", "install", "-q", "torch==2.5.1", "torchvision", "--index-url", idx], timeout=600)

    # vLLM 0.6.3.post1
    log("Installing vLLM 0.6.3.post1 (this may take 5-10 minutes)...")
    run([py, "-m", "pip", "install", "-q", "vllm==0.6.3.post1"], timeout=900)

    log("✅ All dependencies installed")


# ========= MODEL DOWNLOAD =========


def download_model(py: str):
    """Scarica il modello Qwen 32B AWQ da Hugging Face."""
    section("📥 DOWNLOADING QWEN 32B AWQ MODEL")

    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    HF_CACHE.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(HF_CACHE)
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)

    # Controlla se modello già presente
    if (MODEL_PATH / "config.json").exists():
        safetensors = list(MODEL_PATH.glob("*.safetensors"))
        if safetensors:
            log("✅ Model already downloaded")
            return

    log(f"Downloading {MODEL_REPO} (~20GB, may take 15-20 minutes)...")
    log("☕ This is a good time for a coffee break!")

    # Download via huggingface_hub
    code = f"""
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="{MODEL_REPO}",
    local_dir="{MODEL_PATH}",
    max_workers=4
)
"""

    run([py, "-c", code], timeout=7200)
    log("✅ Model downloaded successfully")


def create_chat_template():
    """Crea ChatML template per Qwen."""
    # ChatML template ottimizzato per Qwen
    tpl = r"""{% for message in messages %}{% if loop.first and messages[0]['role'] != 'system' %}<|im_start|>system
You are a helpful assistant.<|im_end|>
{% endif %}<|im_start|>{{ message['role'] }}
{{ message['content'] }}<|im_end|>
{% endfor %}<|im_start|>assistant
"""
    p = MODEL_PATH / "chat_template.jinja"
    p.write_text(tpl)
    log(f"✅ ChatML template created: {p}")
    return p


# ========= vLLM SERVER =========


def start_vllm(py: str):
    """Avvia vLLM server con configurazione ottimizzata."""
    section("🚀 STARTING vLLM SERVER")

    # Kill eventuali processi vLLM esistenti
    run(["pkill", "-9", "-f", "vllm"], check=False)
    time.sleep(2)

    tpl = create_chat_template()

    # Comando vLLM ottimizzato per Qwen 32B AWQ su A40 48GB
    cmd = [
        py,
        "-m",
        "vllm.entrypoints.openai.api_server",
        "--model",
        str(MODEL_PATH),
        "--host",
        "0.0.0.0",
        "--port",
        str(VLLM_PORT),
        "--quantization",
        "awq",  # AWQ quantization
        "--dtype",
        "half",
        "--max-model-len",
        str(MAX_MODEL_LEN),
        "--gpu-memory-utilization",
        str(GPU_MEMORY_UTIL),
        "--max-num-seqs",
        str(MAX_NUM_SEQS),
        "--served-model-name",
        SERVED_MODEL_NAME,
        "--chat-template",
        str(tpl),
        "--trust-remote-code",
        "--enforce-eager",
    ]

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "wb") as lf:
        subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)

    log(f"✅ vLLM server started on port {VLLM_PORT}")


def wait_ready(timeout=900):
    """Attende che vLLM sia pronto (caricamento modello)."""
    section("⏳ LOADING MODEL INTO VRAM")

    import requests

    url = f"http://127.0.0.1:{VLLM_PORT}/v1/models"

    t0 = time.time()
    spin = "|/-\\"
    i = 0

    log("Waiting for model to load (this may take 5-10 minutes)...")
    
    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.ok:
                print()
                elapsed = int(time.time() - t0)
                log(f"✅ Model loaded and ready in {elapsed}s ({elapsed//60}m {elapsed%60}s)")
                return True
        except Exception:
            pass

        print(f"\r{spin[i%4]} Loading... {int(time.time()-t0)}s", end="", flush=True)
        i += 1
        time.sleep(2)

    print()
    log("❌ Timeout waiting for model to load", "ERROR")
    return False


def test_inference():
    """Testa inference con una domanda semplice."""
    section("🧪 TESTING INFERENCE")

    import requests

    try:
        r = requests.post(
            f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions",
            json={
                "model": SERVED_MODEL_NAME,
                "messages": [{"role": "user", "content": "Quanto fa 2+2? Rispondi solo con il numero."}],
                "max_tokens": 10,
                "temperature": 0.1,
            },
            timeout=30,
        )
        response = r.json()
        txt = response["choices"][0]["message"]["content"]
        log(f"✅ Inference test passed. Response: {txt.strip()}")
        return True
    except Exception as e:
        log(f"⚠️  Inference test failed: {e}", "WARN")
        return False


# ========= SSH TUNNEL =========


def setup_tunnel():
    """Configura SSH reverse tunnel verso VPS."""
    section("🚇 SSH REVERSE TUNNEL")

    if not GPU_SSH_PRIVATE_KEY.strip():
        log("⚠️  No SSH key configured (GPU_SSH_PRIVATE_KEY not set)", "WARN")
        log("Skipping tunnel setup. GPU endpoint will be directly accessible.", "WARN")
        return False

    ssh_dir = WORKSPACE / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key = ssh_dir / "gpu_key"

    try:
        key.write_text(GPU_SSH_PRIVATE_KEY)
        os.chmod(key, 0o600)
    except Exception as e:
        log(f"⚠️  Failed to write SSH key: {e}", "WARN")
        return False

    # Test connessione SSH
    log(f"Testing SSH connection to {CPU_USER}@{CPU_HOST}:{CPU_PORT}...")
    try:
        run(
            [
                "ssh",
                "-i",
                str(key),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ConnectTimeout=10",
                "-p",
                str(CPU_PORT),
                f"{CPU_USER}@{CPU_HOST}",
                "echo OK",
            ],
            timeout=15,
        )
        log("✅ SSH connection test successful")
    except subprocess.TimeoutExpired:
        log(f"⚠️  SSH connection to {CPU_USER}@{CPU_HOST}:{CPU_PORT} timed out", "WARN")
        return False
    except subprocess.CalledProcessError as e:
        log(f"⚠️  SSH authentication failed: {e}", "WARN")
        return False
    except Exception as e:
        log(f"⚠️  SSH connection failed: {e}", "WARN")
        return False

    # Kill tunnel esistente
    run(["pkill", "-f", f"ssh.*{CPU_TUNNEL_PORT}"], check=False)
    time.sleep(2)

    # Avvia reverse tunnel
    log(f"Starting reverse tunnel: GPU:{VLLM_PORT} → VPS:{CPU_TUNNEL_PORT}...")
    try:
        subprocess.Popen(
            [
                "ssh",
                "-N",
                "-f",
                "-i",
                str(key),
                "-o",
                "StrictHostKeyChecking=no",
                "-o",
                "ServerAliveInterval=30",
                "-R",
                f"{CPU_TUNNEL_PORT}:127.0.0.1:{VLLM_PORT}",
                "-p",
                str(CPU_PORT),
                f"{CPU_USER}@{CPU_HOST}",
            ]
        )
        time.sleep(2)
        log(f"✅ Reverse tunnel active: GPU:{VLLM_PORT} → VPS:{CPU_TUNNEL_PORT}")
        return True
    except Exception as e:
        log(f"⚠️  Failed to start tunnel: {e}", "WARN")
        return False


# ========= BACKEND REGISTRATION =========


def register_backend(has_tunnel: bool):
    """Registra GPU backend con l'API centrale."""
    section("📡 BACKEND REGISTRATION")

    if not SHARED_SECRET:
        log("⚠️  SHARED_SECRET not configured - skipping backend registration", "WARN")
        return False

    import requests

    # Determina endpoint
    if has_tunnel:
        ep = f"http://127.0.0.1:{CPU_TUNNEL_PORT}/v1/chat/completions"
    else:
        try:
            ip = requests.get("http://checkip.amazonaws.com", timeout=5).text.strip()
        except requests.RequestException as e:
            log(f"⚠️  Could not determine public IP: {e}", "WARN")
            ip = "127.0.0.1"
        ep = f"http://{ip}:{VLLM_PORT}/v1/chat/completions"

    # Payload registrazione
    payload = {
        "llm_endpoint": ep,
        "model": "qwen-32b-instruct",
        "gpu_config": "vast_a40_48gb",
        "context_length": MAX_MODEL_LEN,
        "quantization": "awq-4bit",
        "location": "vast.ai",
    }

    body = json.dumps(payload)
    sig = hmac.new(SHARED_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()

    log(f"Registering endpoint: {ep}")
    try:
        r = requests.post(
            BACKEND_API,
            data=body,
            headers={"Content-Type": "application/json", "X-GPU-Signature": sig},
            timeout=20,
        )
        if r.ok:
            log(f"✅ Backend registration successful")
            log(f"   Endpoint: {ep}")
            return True
        else:
            log(f"⚠️  Backend registration failed with status {r.status_code}: {r.text}", "WARN")
            return False
    except requests.RequestException as e:
        log(f"⚠️  Backend registration request failed: {e}", "WARN")
        return False
    except Exception as e:
        log(f"⚠️  Unexpected error during registration: {e}", "WARN")
        return False


# ========= MAIN =========


def main():
    """Main setup flow."""
    section("🚀 QUANTUMDEV GPU SETUP - QWEN 32B AWQ")
    
    start_time = time.time()
    
    # Invia notifica inizio
    notify_start()
    
    try:
        # Rileva ambiente
        env = Env()
        env.summary()

        # Setup Python environment
        py = ensure_venv()
        install_deps(py, env.cuda_major)

        # Download modello
        download_model(py)

        # Avvia vLLM
        start_vllm(py)
        if not wait_ready():
            raise RuntimeError("vLLM failed to start or model failed to load")

        # Test inference
        test_inference()

        # Setup tunnel e registrazione
        has_tunnel = setup_tunnel()
        register_backend(has_tunnel)

        # Summary finale
        elapsed = int(time.time() - start_time)
        section("✅ SETUP COMPLETE")
        log(f"⏱️  Total time: {elapsed//60}m {elapsed%60}s")
        log(f"🌐 Endpoint: http://0.0.0.0:{VLLM_PORT}")
        log(f"🤖 Model: {SERVED_MODEL_NAME}")
        log(f"📝 Context: {MAX_MODEL_LEN} tokens")
        log(f"💾 GPU Memory: {int(GPU_MEMORY_UTIL*100)}%")
        if has_tunnel:
            log(f"🚇 Tunnel: VPS port {CPU_TUNNEL_PORT}")
        log("")
        log("🎉 GPU is operational and ready to serve requests!")
        
        # Invia notifica successo
        notify_success(elapsed)
        
        return 0
        
    except Exception as e:
        error_msg = str(e)
        log(f"❌ Setup failed: {error_msg}", "ERROR")
        notify_error(error_msg)
        raise


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        log("⚠️  Setup interrupted by user", "WARN")
        notify_error("Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"❌ Fatal error: {e}", "ERROR")
        import traceback
        traceback.print_exc()
        sys.exit(1)
