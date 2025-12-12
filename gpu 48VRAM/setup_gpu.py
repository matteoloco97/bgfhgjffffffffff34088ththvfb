#!/usr/bin/env python3
"""
setup_gpu.py — QWEN 32B AWQ GPU Setup (FULLY AUTOMATED)

Complete autonomous setup for QuantumDev with:
- Qwen 2.5 32B Instruct AWQ
- Telegram notifications
- Backend registration
- Health checks
- Zero manual intervention

Configured for: Vast.ai A40 48GB
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

# ========= CONFIG =========

WORKSPACE = Path("/workspace")
VENV_DIR = Path("/venv/main")
LOG_FILE = WORKSPACE / "setup_gpu.log"
LOG_PATH = WORKSPACE / "vllm.log"

MODEL_PATH = WORKSPACE / "models" / "qwen-32b-awq"
HF_CACHE = WORKSPACE / "hf_cache"

# Model configuration
MODEL_REPO = "Qwen/Qwen2.5-32B-Instruct-AWQ"
SERVED_MODEL_NAME = "qwen"
VLLM_PORT = 9011

# Optimized for A40 48GB
MAX_MODEL_LEN = 32768
GPU_MEMORY_UTIL = 0.85
MAX_NUM_SEQS = 8

# Load environment
CPU_HOST = os.getenv("CPU_HOST", "")
CPU_USER = os.getenv("CPU_USER", "root")
CPU_PORT = int(os.getenv("CPU_PORT", "22"))
CPU_TUNNEL_PORT = int(os.getenv("CPU_TUNNEL_PORT", "9011"))
GPU_SSH_PRIVATE_KEY = os.getenv("GPU_SSH_PRIVATE_KEY", "").strip()
BACKEND_API = os.getenv("BACKEND_API", "")
SHARED_SECRET = os.getenv("SHARED_SECRET", "").strip()

# Telegram notification
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_ADMIN_ID = os.getenv("TELEGRAM_ADMIN_ID", "")

CORRELATION_ID = str(uuid.uuid4())[:8]

# ========= Logging =========

def log(msg: str, level="INFO"):
    """Log with timestamp and correlation ID."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{CORRELATION_ID}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def section(title: str):
    log("=" * 80)
    log(title)
    log("=" * 80)


def send_telegram(message: str):
    """Send Telegram notification."""
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_ID:
        return
    
    try:
        import requests
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        requests.post(url, json={
            "chat_id": TELEGRAM_ADMIN_ID,
            "text": f"🔧 QuantumDev GPU Setup\n\n{message}",
            "parse_mode": "Markdown"
        }, timeout=10)
    except Exception as e:
        log(f"Telegram notification failed: {e}", "WARN")


# ========= Environment =========

class Env:
    def __init__(self):
        self.cuda_major = self._cuda_major()

    def _cuda_major(self):
        try:
            v = subprocess.check_output(["nvcc", "--version"], text=True)
            m = re.search(r"release (\d+)\.", v)
            return int(m.group(1)) if m else 12
        except Exception:
            log("⚠️  nvcc not found, assuming CUDA 12", "WARN")
            return 12

    def summary(self):
        section("📊 ENVIRONMENT")
        log(f"Python: {sys.version.split()[0]}")
        log(f"CUDA: {self.cuda_major}.x")
        log(f"Model: {MODEL_REPO}")
        log(f"Port: {VLLM_PORT}")
        log(f"Context: {MAX_MODEL_LEN} tokens")
        log(f"Workspace: {WORKSPACE}")


def run(cmd, check=True, timeout=None):
    log(f"$ {' '.join(str(x) for x in cmd)}")
    return subprocess.run(cmd, check=check, timeout=timeout, text=True)


# ========= Virtual Environment =========

def ensure_venv():
    section("🐍 VIRTUAL ENVIRONMENT")
    VENV_DIR.mkdir(parents=True, exist_ok=True)
    py = VENV_DIR / "bin" / "python"

    if not py.exists():
        log("Creating venv...")
        run([sys.executable, "-m", "venv", str(VENV_DIR)])

    log(f"✅ {py}")
    return str(py)


# ========= Dependencies =========

def install_deps(py: str, cuda_major: int):
    section("📦 DEPENDENCIES")

    run([py, "-m", "pip", "install", "--upgrade", "pip"], timeout=300)

    log("Installing PyTorch 2.4.0 (required by vLLM)...")
    torch_cmd = [
        py, "-m", "pip", "install",
        "torch==2.4.0", "torchvision==0.19.0", "torchaudio",
        "--index-url", f"https://download.pytorch.org/whl/cu{cuda_major}1",
    ]
    run(torch_cmd, timeout=900)

    log("Installing vLLM...")
    run([py, "-m", "pip", "install", "vllm==0.6.3.post1"], timeout=900)

    log("Installing utilities...")
    run([py, "-m", "pip", "install", "huggingface-hub", "requests"], timeout=300)

    log("✅ Dependencies installed")


def download_model(py: str):
    section("📥 MODEL DOWNLOAD")

    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    HF_CACHE.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(HF_CACHE)
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)

    if (MODEL_PATH / "config.json").exists():
        safetensors = list(MODEL_PATH.glob("*.safetensors"))
        if safetensors:
            log("✅ Model already present")
            return

    log("Downloading Qwen 32B AWQ (~16GB, 10-15 min on A40)...")
    log("☕ This is a good time for coffee...")

    send_telegram("📥 Starting model download (16GB)...\nETA: ~10 minutes")

    code = f"""
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="{MODEL_REPO}",
    local_dir="{MODEL_PATH}",
    max_workers=4
)
"""

    run([py, "-c", code], timeout=7200)
    log("✅ Model downloaded")
    send_telegram("✅ Model download complete!")


def create_template():
    """Create Qwen ChatML template."""
    tpl = r"""{% for message in messages %}{% if message['role'] == 'system' %}<|im_start|>system
{{ message['content'] }}<|im_end|>
{% elif message['role'] == 'user' %}<|im_start|>user
{{ message['content'] }}<|im_end|>
{% elif message['role'] == 'assistant' %}<|im_start|>assistant
{{ message['content'] }}<|im_end|>
{% endif %}{% endfor %}{% if add_generation_prompt %}<|im_start|>assistant
{% endif %}"""
    
    p = MODEL_PATH / "template.jinja"
    p.write_text(tpl)
    return p


# ========= vLLM =========

def start_vllm(py: str):
    section("🚀 VLLM SERVER")

    run(["pkill", "-9", "-f", "vllm"], check=False)
    time.sleep(2)

    tpl = create_template()

    cmd = [
        py, "-m", "vllm.entrypoints.openai.api_server",
        "--model", str(MODEL_PATH),
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--quantization", "awq",
        "--dtype", "half",
        "--max-model-len", str(MAX_MODEL_LEN),
        "--gpu-memory-utilization", str(GPU_MEMORY_UTIL),
        "--max-num-seqs", str(MAX_NUM_SEQS),
        "--served-model-name", SERVED_MODEL_NAME,
        "--chat-template", str(tpl),
        "--trust-remote-code",
        "--enforce-eager",
        "--disable-log-requests",
    ]

    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    
    log(f"Starting vLLM on port {VLLM_PORT}...")
    send_telegram(f"🚀 Starting vLLM server...\nLoading model into GPU memory...")
    
    with open(LOG_PATH, "wb") as lf:
        subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)

    log("✅ vLLM process started")


def wait_ready(timeout=1200):
    """Wait for vLLM to be ready."""
    section("⏳ LOADING MODEL INTO VRAM")

    import requests

    url = f"http://127.0.0.1:{VLLM_PORT}/v1/models"

    t0 = time.time()
    spin = "|/-\\"
    i = 0
    last_notify = 0

    log("Loading 32B model into 48GB VRAM...")
    log("This takes 5-10 minutes on A40...")

    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=5)
            if r.ok:
                print()
                elapsed = int(time.time() - t0)
                log(f"✅ MODEL LOADED in {elapsed}s ({elapsed//60}m {elapsed%60}s)")
                send_telegram(f"✅ vLLM ready!\nLoad time: {elapsed//60}m {elapsed%60}s")
                return True
        except Exception:
            pass

        elapsed = int(time.time() - t0)
        
        # Notify every 3 minutes
        if elapsed - last_notify >= 180:
            send_telegram(f"⏳ Still loading model...\nElapsed: {elapsed//60}m")
            last_notify = elapsed

        print(f"\r{spin[i%4]} {elapsed}s ({elapsed//60}m {elapsed%60}s)", end="", flush=True)
        i += 1
        time.sleep(3)

    print()
    log("❌ Timeout waiting for vLLM", "ERROR")
    send_telegram(f"❌ Setup failed: vLLM timeout\nCheck logs at /workspace/vllm.log")
    return False


def test():
    section("🧪 INFERENCE TEST")

    import requests

    try:
        log("Testing inference...")
        r = requests.post(
            f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions",
            json={
                "model": SERVED_MODEL_NAME,
                "messages": [{"role": "user", "content": "Rispondi solo 'OK' e nient'altro."}],
                "max_tokens": 5,
                "temperature": 0,
            },
            timeout=30,
        )
        
        if not r.ok:
            log(f"⚠️  HTTP {r.status_code}: {r.text}", "WARN")
            return False
            
        data = r.json()
        txt = data["choices"][0]["message"]["content"]
        log(f"✅ Response: {txt}")
        return True
        
    except Exception as e:
        log(f"⚠️  Test failed: {e}", "WARN")
        return False


def register():
    """Register GPU with backend."""
    section("📡 BACKEND REGISTRATION")

    if not SHARED_SECRET or not BACKEND_API:
        log("⚠️  Backend registration not configured", "WARN")
        return False

    import requests

    try:
        # Get public IP
        ip = requests.get("http://checkip.amazonaws.com", timeout=5).text.strip()
        ep = f"http://{ip}:{VLLM_PORT}/v1/chat/completions"
    except Exception:
        log("⚠️  Could not determine public IP", "WARN")
        ep = f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions"

    payload = {
        "llm_endpoint": ep,
        "model": SERVED_MODEL_NAME,
        "gpu_config": "vast_a40_48gb",
        "context_length": MAX_MODEL_LEN,
        "quantization": "awq",
        "location": "vast.ai_belgium",
    }

    body = json.dumps(payload)
    sig = hmac.new(SHARED_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()

    try:
        r = requests.post(
            BACKEND_API,
            data=body,
            headers={"Content-Type": "application/json", "X-GPU-Signature": sig},
            timeout=20,
        )
        if r.ok:
            log(f"✅ Registered at {ep}")
            return True
        else:
            log(f"⚠️  Registration failed: HTTP {r.status_code}", "WARN")
            return False
    except Exception as e:
        log(f"⚠️  Registration error: {e}", "WARN")
        return False


# ========= Main =========

def main():
    section("🚀 QUANTUMDEV GPU SETUP - QWEN 32B AWQ")
    
    send_telegram(f"🚀 *GPU Setup Started*\nCorrelation ID: `{CORRELATION_ID}`\nModel: Qwen 32B AWQ\nGPU: Vast.ai A40 48GB")

    env = Env()
    env.summary()

    py = ensure_venv()
    install_deps(py, env.cuda_major)
    download_model(py)
    start_vllm(py)
    
    if not wait_ready():
        log("❌ vLLM failed to start", "ERROR")
        log(f"Check logs: tail -f {LOG_PATH}", "ERROR")
        return 1

    if not test():
        log("⚠️  Test inference failed, but vLLM is running", "WARN")
    
    register()

    section("✅ SETUP COMPLETE")
    log(f"Endpoint: http://0.0.0.0:{VLLM_PORT}")
    log(f"Model: {SERVED_MODEL_NAME}")
    log(f"Context: {MAX_MODEL_LEN} tokens")
    log(f"Logs: {LOG_PATH}")
    log("")
    log("🎉 GPU OPERATIONAL!")
    
    # Final success notification
    send_telegram(
        f"🎉 *Setup Complete!*\n\n"
        f"✅ vLLM running on port {VLLM_PORT}\n"
        f"✅ Model: {SERVED_MODEL_NAME}\n"
        f"✅ Context: {MAX_MODEL_LEN} tokens\n\n"
        f"Next: Create tunnel from VPS\n"
        f"`ssh -N -L 9011:localhost:9011 root@<gpu-ip> -p <gpu-port>`"
    )
    
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        log("⚠️  Interrupted", "WARN")
        send_telegram("⚠️ Setup interrupted by user")
        sys.exit(1)
    except Exception as e:
        log(f"❌ Fatal error: {e}", "ERROR")
        send_telegram(f"❌ *Setup Failed*\n\nError: `{e}`")
        import traceback
        traceback.print_exc()
        sys.exit(1)
