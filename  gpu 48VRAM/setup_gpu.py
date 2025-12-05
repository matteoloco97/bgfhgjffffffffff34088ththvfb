#!/usr/bin/env python3
"""
setup_gpu.py — FULLY AUTONOMOUS GPU Setup (PRODUCTION READY)

Zero interaction. Handles all edge cases.
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

MODEL_PATH = WORKSPACE / "models" / "dolphin-24b-venice-awq"
HF_CACHE = WORKSPACE / "hf_cache"

MODEL_REPO = "warshanks/Dolphin-Mistral-24B-Venice-Edition-AWQ"
SERVED_MODEL_NAME = "llama-3.1-70b"
VLLM_PORT = 8001

MAX_MODEL_LEN = 3072
GPU_MEMORY_UTIL = 0.80
MAX_NUM_SEQS = 1

# Load configuration from environment variables
CPU_HOST = os.getenv("CPU_HOST")
CPU_USER = os.getenv("CPU_USER", "gpu-tunnel")
CPU_PORT = int(os.getenv("CPU_PORT", "22"))
CPU_TUNNEL_PORT = int(os.getenv("CPU_TUNNEL_PORT", "9001"))

GPU_SSH_PRIVATE_KEY = os.getenv("GPU_SSH_PRIVATE_KEY", "").strip()

BACKEND_API = os.getenv("BACKEND_API")
SHARED_SECRET = os.getenv("SHARED_SECRET", "").strip()

# Generate correlation ID for this setup run
CORRELATION_ID = str(uuid.uuid4())[:8]

# ========= Logging =========


def log(msg: str, level="INFO"):
    """Log message with timestamp, correlation ID, and level."""
    ts = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] [{CORRELATION_ID}] [{level}] {msg}"
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception as e:
        # Only fail silently for logging errors
        print(f"Warning: Could not write to log file: {e}", file=sys.stderr)


def section(title: str):
    log("=" * 80)
    log(title)
    log("=" * 80)


def validate_environment():
    """Validate that all required environment variables are set."""
    section("🔍 ENVIRONMENT VALIDATION")

    missing = []
    warnings = []

    # Required variables
    if not CPU_HOST:
        missing.append("CPU_HOST - The hostname/IP of the CPU server")

    if not BACKEND_API:
        missing.append("BACKEND_API - The backend API endpoint for registration")

    # Optional but recommended variables
    if not GPU_SSH_PRIVATE_KEY:
        warnings.append("GPU_SSH_PRIVATE_KEY - SSH tunnel will be disabled")

    if not SHARED_SECRET:
        warnings.append("SHARED_SECRET - Backend registration will be disabled")

    if missing:
        log("❌ MISSING REQUIRED ENVIRONMENT VARIABLES:", "ERROR")
        for var in missing:
            log(f"  - {var}", "ERROR")
        log("", "ERROR")
        log("Please set the required environment variables and try again.", "ERROR")
        log("See .env.example for a template.", "ERROR")
        raise OSError(
            f"Missing required environment variables: {', '.join([v.split(' - ')[0] for v in missing])}"
        )

    if warnings:
        log("⚠️  Optional environment variables not set:", "WARN")
        for var in warnings:
            log(f"  - {var}", "WARN")

    log("✅ Environment validation passed")
    log(f"Correlation ID: {CORRELATION_ID}")


# ========= Env =========


class Env:
    def __init__(self):
        self.cuda_version = self._cuda_version()
        self.cuda_major = int(self.cuda_version.split(".")[0]) if self.cuda_version else 12
        self.gpu_name = self._gpu_name()
        self.vram_gb = self._vram_gb()

    def _cuda_version(self) -> str:
        try:
            r = subprocess.run(["nvidia-smi"], capture_output=True, text=True, timeout=5)
            m = re.search(r"CUDA Version:\s+(\d+\.\d+)", r.stdout)
            if m:
                return m.group(1)
        except Exception:
            pass
        return "12.1"

    def _gpu_name(self) -> str:
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
        section("🔍 ENVIRONMENT")
        log(f"GPU  : {self.gpu_name}")
        log(f"VRAM : {self.vram_gb} GB")
        log(f"CUDA : {self.cuda_version} (major: {self.cuda_major})")


def run(cmd, check=True, shell=False, timeout=None):
    try:
        return subprocess.run(
            cmd, check=check, shell=shell, timeout=timeout, capture_output=False, text=True
        )
    except subprocess.CalledProcessError:
        if check:
            log(f"Command failed: {' '.join(cmd) if isinstance(cmd, list) else cmd}", "ERROR")
            raise
        return None


# ========= Install =========


def ensure_venv() -> str:
    section("🐍 VENV")
    if not VENV_DIR.exists():
        VENV_DIR.mkdir(parents=True, exist_ok=True)
        run(["python3", "-m", "venv", str(VENV_DIR)])
    py = str(VENV_DIR / "bin" / "python")
    run([py, "-m", "pip", "install", "-q", "--upgrade", "pip"], check=False)
    log("✅ venv ready")
    return py


def install_deps(py: str, cuda_major: int):
    section("📦 DEPENDENCIES")

    # Base (no hf_transfer to avoid issues)
    log("Base packages...")
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

    # PyTorch
    log("PyTorch...")
    idx = (
        "https://download.pytorch.org/whl/cu121"
        if cuda_major >= 12
        else "https://download.pytorch.org/whl/cu118"
    )
    run([py, "-m", "pip", "install", "-q", "torch", "torchvision", "--index-url", idx], timeout=600)

    # vLLM
    log("vLLM (this takes 5-10 min)...")
    if cuda_major >= 12:
        run([py, "-m", "pip", "install", "-q", "vllm>=0.7.3,<0.9"], timeout=900)
    else:
        run([py, "-m", "pip", "install", "-q", "vllm==0.6.3.post1"], timeout=900)

    log("✅ Dependencies OK")


def download_model(py: str):
    section("📥 MODEL DOWNLOAD")

    MODEL_PATH.mkdir(parents=True, exist_ok=True)
    HF_CACHE.mkdir(parents=True, exist_ok=True)

    os.environ["HF_HOME"] = str(HF_CACHE)
    # DON'T enable hf_transfer - it causes issues
    os.environ.pop("HF_HUB_ENABLE_HF_TRANSFER", None)

    if (MODEL_PATH / "config.json").exists():
        safetensors = list(MODEL_PATH.glob("*.safetensors"))
        if safetensors:
            log("✅ Model already present")
            return

    log("Downloading 13GB model (10-15 min)...")
    log("Go get coffee ☕")

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


def create_template():
    tpl = r"""{{ bos_token }}{% for m in messages %}{% if m['role'] == 'user' %}[INST] {{ m['content'] }} [/INST]{% elif m['role'] == 'assistant' %} {{ m['content'] }}{% endif %}{% endfor %}"""
    p = MODEL_PATH / "template.jinja"
    p.write_text(tpl)
    return p


# ========= vLLM =========


def start_vllm(py: str):
    section("🚀 VLLM")

    run(["pkill", "-9", "-f", "vllm"], check=False)
    time.sleep(2)

    tpl = create_template()

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
        "compressed-tensors",
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

    log("✅ Started")


def wait_ready(timeout=900):
    section("⏳ LOADING MODEL")

    import requests

    url = f"http://127.0.0.1:{VLLM_PORT}/v1/models"

    t0 = time.time()
    spin = "|/-\\"
    i = 0

    while time.time() - t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.ok:
                print()
                log(f"✅ READY in {int(time.time()-t0)}s")
                return True
        except Exception:
            pass

        print(f"\r{spin[i%4]} {int(time.time()-t0)}s", end="", flush=True)
        i += 1
        time.sleep(2)

    print()
    log("❌ Timeout", "ERROR")
    return False


def test():
    section("🧪 TEST")

    import requests

    try:
        r = requests.post(
            f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions",
            json={
                "model": SERVED_MODEL_NAME,
                "messages": [{"role": "user", "content": "2+2=?"}],
                "max_tokens": 5,
            },
            timeout=30,
        )
        txt = r.json()["choices"][0]["message"]["content"]
        log(f"✅ {txt}")
        return True
    except Exception as e:
        log(f"⚠️  {e}", "WARN")
        return False


# ========= Tunnel =========


def tunnel():
    section("🚇 TUNNEL")

    if not GPU_SSH_PRIVATE_KEY.strip():
        log("⚠️  No SSH key configured (GPU_SSH_PRIVATE_KEY not set)", "WARN")
        log("Skipping tunnel setup. GPU endpoint will be directly accessible.", "WARN")
        return False

    ssh_dir = WORKSPACE / ".ssh"
    ssh_dir.mkdir(mode=0o700, exist_ok=True)
    key = ssh_dir / "key"

    try:
        key.write_text(GPU_SSH_PRIVATE_KEY)
        os.chmod(key, 0o600)
    except Exception as e:
        log(f"⚠️  Failed to write SSH key: {e}", "WARN")
        return False

    # Test SSH connection
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
    except subprocess.TimeoutExpired:
        log(f"⚠️  SSH connection to {CPU_USER}@{CPU_HOST}:{CPU_PORT} timed out", "WARN")
        return False
    except subprocess.CalledProcessError as e:
        log(f"⚠️  SSH authentication failed: {e}", "WARN")
        return False
    except Exception as e:
        log(f"⚠️  SSH connection failed: {e}", "WARN")
        return False

    # Kill existing tunnel
    run(["pkill", "-f", f"ssh.*{CPU_TUNNEL_PORT}"], check=False)
    time.sleep(2)

    # Start tunnel
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
        log(f"✅ GPU:{VLLM_PORT} → CPU:{CPU_TUNNEL_PORT}")
        return True
    except Exception as e:
        log(f"⚠️  Failed to start tunnel: {e}", "WARN")
        return False


def register(has_tunnel: bool):
    section("📡 BACKEND")

    if not SHARED_SECRET:
        log("⚠️  SHARED_SECRET not configured - skipping backend registration", "WARN")
        return False

    import requests

    if has_tunnel:
        ep = f"http://127.0.0.1:{CPU_TUNNEL_PORT}/v1/chat/completions"
    else:
        try:
            ip = requests.get("http://checkip.amazonaws.com", timeout=5).text.strip()
        except requests.RequestException as e:
            log(f"⚠️  Could not determine public IP: {e}", "WARN")
            ip = "127.0.0.1"
        ep = f"http://{ip}:{VLLM_PORT}/v1/chat/completions"

    payload = {
        "llm_endpoint": ep,
        "model": "dolphin-24b-venice",
        "gpu_config": "vast_48gb",
        "context_length": MAX_MODEL_LEN,
        "quantization": "compressed-tensors-4bit",
        "location": "vast.ai",
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
            log(f"⚠️  Backend registration failed with status {r.status_code}: {r.text}", "WARN")
            return False
    except requests.RequestException as e:
        log(f"⚠️  Backend registration request failed: {e}", "WARN")
        return False
    except Exception as e:
        log(f"⚠️  Unexpected error during registration: {e}", "WARN")
        return False


# ========= Main =========


def main():
    section("🚀 QUANTUM GPU SETUP")

    # Validate environment variables first
    validate_environment()

    env = Env()
    env.summary()

    py = ensure_venv()
    install_deps(py, env.cuda_major)
    download_model(py)

    start_vllm(py)
    if not wait_ready():
        log("❌ vLLM failed to start", "ERROR")
        return 1

    test()

    has_tunnel = tunnel()
    register(has_tunnel)

    section("✅ COMPLETE")
    log(f"Endpoint: http://0.0.0.0:{VLLM_PORT}")
    log(f"Model: {SERVED_MODEL_NAME}")
    log(f"Context: {MAX_MODEL_LEN} tokens")
    if has_tunnel:
        log(f"Tunnel: CPU port {CPU_TUNNEL_PORT}")
    log("")
    log("🎉 GPU operational!")

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        log("⚠️  Interrupted", "WARN")
        sys.exit(1)
    except Exception as e:
        log(f"❌ {e}", "ERROR")
        import traceback

        traceback.print_exc()
        sys.exit(1)
