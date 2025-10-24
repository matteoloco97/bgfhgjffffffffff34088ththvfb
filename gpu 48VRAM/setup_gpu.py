#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_gpu.py  —  QuantumDev GPU bootstrap (virgin → production ready)

Target model: Dolphin-Mistral-24B-Venice-Edition-AWQ (quantized for vLLM)
Use-case: single vLLM endpoint shared by personal (uncensored) & client (filtered) faces
GPU: RTX 8000 / RTX 6000 Ada (~48GB; works on >=24GB)
API contract: OpenAI-style, served-model-name kept stable ('llama-3.1-70b')

Actions:
  - check     → preflight (GPU/CUDA/disk/ports)
  - deps      → create/upgrade venv + install pinned deps
  - download  → download model + tokenizer (auto-fix if missing)
  - run       → start vLLM only
  - full      → check + deps + download + run + wait + test + register + tunnel
  - validate  → validate local model folder
  - test      → quick inference test against running server
"""

import os
import sys
import time
import json
import shutil
import subprocess
import hmac
import hashlib
from pathlib import Path

# ================== TUNNEL CONFIGURATION ==================
from dotenv import load_dotenv

# Carica .env se presente (sarà creato al primo avvio)
ENV_PATH = Path("/workspace/.env")
if ENV_PATH.exists():
    load_dotenv(ENV_PATH)

CPU_SSH_HOST = os.environ.get("CPU_SSH_HOST", "")
CPU_SSH_USER = os.environ.get("CPU_SSH_USER", "gpu-tunnel")
CPU_SSH_PORT = int(os.environ.get("CPU_SSH_PORT", "22"))
CPU_TUNNEL_PORT = int(os.environ.get("CPU_TUNNEL_PORT", "9001"))
GPU_KEY_PATH = Path("/workspace/.ssh/gpu_tunnel_key")

# ================== GLOBAL CONFIG ==================

VENV_DIR = Path("/venv/main")
PYTHON = str(VENV_DIR / "bin/python") if VENV_DIR.exists() else "python3"

# Model repos
MODEL_REPO = "warshanks/Dolphin-Mistral-24B-Venice-Edition-AWQ"
TOKENIZER_BASE_REPO = "mistralai/Mistral-Small-24B-Instruct-2501"

# Local paths
WORKSPACE = Path("/workspace")
MODELS_DIR = WORKSPACE / "models"
MODEL_PATH = MODELS_DIR / "dolphin-24b-venice-awq"
HF_CACHE = WORKSPACE / "hf_cache"

# API & runtime
MODEL_ALIAS_INTERNAL = "dolphin-24b-venice"
SERVED_MODEL_NAME = "llama-3.1-70b"
VLLM_PORT = int(os.environ.get("VLLM_PORT", "8001"))
LOG_PATH = WORKSPACE / "vllm_dolphin24b.log"
WAIT_TIMEOUT = 2400

# Tuning memoria (anti-OOM) - conservativo per production
GPU_MEMORY_UTIL = 0.85
MAX_MODEL_LEN   = 4096
MAX_NUM_SEQS    = 2

# Backend registration (HMAC)
QUANTUM_BACKEND_API = os.environ.get(
    "QUANTUM_BACKEND_API", 
    "http://84.247.166.247:8081/update_gpu"
)
QUANTUM_SHARED_SECRET = os.environ.get(
    "QUANTUM_SHARED_SECRET",
    "5e6ad9f7c2b14dceb2f4a1a9087c3da0d4a885c3e85f1b2d47a6f0e9c3b21d77"
)

REQUIRED_FILES = ["config.json", "generation_config.json"]
REQUIRED_TOKENIZER_ANY = ["tokenizer.json", "tokenizer.model"]
REQUIRED_TOKENIZER_EXTRA = ["tokenizer_config.json", "special_tokens_map.json"]

# ================== UTILS ==================

def sh(cmd, check=True, capture=False, env=None, timeout=None):
    if isinstance(cmd, str):
        shell=True; printable = cmd
    else:
        shell=False; printable = " ".join(str(c) for c in cmd)
    print(f"\n💻 $ {printable}")
    try:
        if capture:
            res = subprocess.run(cmd, check=check, capture_output=True, text=True,
                                 env=env, timeout=timeout, shell=shell)
            if res.stdout: print(res.stdout.strip())
            if res.stderr and (not check): print(res.stderr.strip())
            return res
        return subprocess.run(cmd, check=check, env=env, timeout=timeout, shell=shell)
    except subprocess.CalledProcessError as e:
        print(f"❌ Command failed (code {e.returncode})")
        if e.stdout: print(e.stdout)
        if e.stderr: print(e.stderr)
        if check: raise
        return e
    except subprocess.TimeoutExpired:
        print(f"⚠️ Timeout after {timeout}s")
        if check: raise

def ensure_dirs():
    HF_CACHE.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.mkdir(parents=True, exist_ok=True)

def env_base():
    env = os.environ.copy()
    env["HF_HOME"] = str(HF_CACHE)
    env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    env["HF_HUB_DOWNLOAD_TIMEOUT"] = "3600"
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")
    return env

def print_header(title):
    print("\n" + "="*80)
    print(title)
    print("="*80)

# ================== ENV SETUP ==================

def create_gpu_env_interactive():
    """Crea .env interattivamente se non esiste"""
    print_header("🔧 SETUP GPU .env")
    
    if ENV_PATH.exists():
        print(f"✅ File .env già esistente: {ENV_PATH}")
        return True
    
    print("📝 Il file .env non esiste. Creazione guidata...")
    print("")
    print("Per connettersi alla CPU, ho bisogno di alcune informazioni.")
    print("Puoi trovarle sulla CPU in: /root/quantumdev-open/config/gpu-tunnel/")
    print("")
    
    # Valori di default sensati
    default_cpu_host = "84.247.166.247"
    default_cpu_user = "gpu-tunnel"
    default_cpu_port = "22"
    default_tunnel_port = "9001"
    default_backend_api = "http://84.247.166.247:8081/update_gpu"
    default_secret = "5e6ad9f7c2b14dceb2f4a1a9087c3da0d4a885c3e85f1b2d47a6f0e9c3b21d77"
    
    # Input interattivo con defaults
    cpu_host = input(f"CPU Host [{default_cpu_host}]: ").strip() or default_cpu_host
    cpu_user = input(f"CPU User [{default_cpu_user}]: ").strip() or default_cpu_user
    cpu_port = input(f"CPU Port [{default_cpu_port}]: ").strip() or default_cpu_port
    tunnel_port = input(f"Tunnel Port [{default_tunnel_port}]: ").strip() or default_tunnel_port
    
    print("")
    print("📋 Adesso ho bisogno della CHIAVE SSH PRIVATA.")
    print("   Sulla CPU, esegui:")
    print("   cat /root/quantumdev-open/config/gpu-tunnel/gpu_private_key")
    print("")
    print("   Copia TUTTA la chiave (da -----BEGIN a -----END)")
    print("   e incollala qui (premi ENTER due volte quando hai finito):")
    print("")
    
    key_lines = []
    while True:
        line = input()
        if not line and key_lines:  # Due ENTER di fila
            break
        if line:
            key_lines.append(line)
    
    ssh_key = "\n".join(key_lines)
    
    if not ssh_key.startswith("-----BEGIN"):
        print("⚠️ La chiave non sembra valida. Proseguo comunque...")
    
    backend_api = input(f"Backend API [{default_backend_api}]: ").strip() or default_backend_api
    secret = input(f"Shared Secret [{default_secret[:20]}...]: ").strip() or default_secret
    
    # Crea il file
    env_content = f"""# =========================================
# GPU .env - Auto-generated by setup_gpu.py
# =========================================

# === CPU Connection (Reverse SSH Tunnel) ===
CPU_SSH_HOST={cpu_host}
CPU_SSH_USER={cpu_user}
CPU_SSH_PORT={cpu_port}
CPU_TUNNEL_PORT={tunnel_port}

# === SSH Private Key ===
GPU_SSH_PRIVATE_KEY="{ssh_key}"

# === Backend Registration ===
QUANTUM_BACKEND_API={backend_api}
QUANTUM_SHARED_SECRET={secret}
"""
    
    ENV_PATH.write_text(env_content, encoding="utf-8")
    os.chmod(ENV_PATH, 0o600)
    
    print("")
    print(f"✅ File .env creato: {ENV_PATH}")
    print("")
    print("🔄 Ricarico variabili d'ambiente...")
    load_dotenv(ENV_PATH)
    
    # Aggiorna variabili globali
    global CPU_SSH_HOST, CPU_SSH_USER, CPU_SSH_PORT, CPU_TUNNEL_PORT
    global QUANTUM_BACKEND_API, QUANTUM_SHARED_SECRET
    
    CPU_SSH_HOST = os.environ.get("CPU_SSH_HOST", cpu_host)
    CPU_SSH_USER = os.environ.get("CPU_SSH_USER", cpu_user)
    CPU_SSH_PORT = int(os.environ.get("CPU_SSH_PORT", cpu_port))
    CPU_TUNNEL_PORT = int(os.environ.get("CPU_TUNNEL_PORT", tunnel_port))
    QUANTUM_BACKEND_API = os.environ.get("QUANTUM_BACKEND_API", backend_api)
    QUANTUM_SHARED_SECRET = os.environ.get("QUANTUM_SHARED_SECRET", secret)
    
    return True

# ================== PREFLIGHT ==================

def check_gpu():
    print_header("🔍 GPU CHECK")
    try:
        res = sh(["nvidia-smi","--query-gpu=index,name,memory.total","--format=csv,noheader,nounits"], capture=True)
        idx, name, total_mb = [x.strip() for x in res.stdout.strip().splitlines()[0].split(",")]
        total_gb = int(total_mb) / 1024
        print(f"GPU {idx}: {name}  |  VRAM: {total_gb:.1f} GB")
        if total_gb < 24:
            print("❌ Need ≥ 24GB for 24B@INT4 with 4K context."); return False
        print("✅ GPU OK"); return True
    except Exception as e:
        print(f"❌ Cannot read GPU info: {e}"); return False

def check_cuda():
    print_header("🔍 CUDA / PyTorch CHECK")
    code = ("import torch, json; "
            "print(json.dumps({'torch': torch.__version__, 'cuda': torch.version.cuda, 'is_cuda': torch.cuda.is_available()}))")
    try:
        res = sh([PYTHON, "-c", code], capture=True)
        info = json.loads(res.stdout.strip())
        print(f"PyTorch: {info['torch']} | CUDA: {info['cuda']} | GPU available: {info['is_cuda']}")
        if not info["is_cuda"]:
            print("❌ PyTorch does not see the GPU"); return False
        print("✅ CUDA OK"); return True
    except Exception as e:
        print(f"❌ CUDA/PyTorch check failed: {e}"); return False

def check_disk():
    print_header("💾 DISK CHECK (/workspace)")
    try:
        res = sh(["df","-h","/workspace"], capture=True)
        lines = res.stdout.strip().splitlines()
        print("\n".join(lines))
        parts = lines[1].split(); avail = parts[3]
        num = float(avail[:-1]); unit = avail[-1]
        avail_gb = num * (1024 if unit.upper()=="T" else 1)
        need_gb = 26 + 12
        if avail_gb < need_gb:
            print(f"❌ Low space. Need ≥ ~{need_gb} GB free."); return False
        print("✅ Disk OK"); return True
    except Exception as e:
        print(f"⚠️ Disk check error: {e}"); return True

def check_port_free():
    print_header(f"🔌 PORT CHECK (tcp:{VLLM_PORT})")
    out = sh(["bash","-lc", f"if command -v lsof >/dev/null; then lsof -i TCP:{VLLM_PORT} -sTCP:LISTEN || true; fi"], capture=True, check=False)
    if out and out.stdout and "LISTEN" in out.stdout:
        print("⚠️ Port busy. Killing old vLLM.")
        sh(["pkill","-9","-f","vllm"], check=False)
        time.sleep(2)
    print("✅ Port ready")

def preflight():
    ok = True
    ok &= check_gpu()
    ok &= check_disk()
    return ok

# ================== VENV & DEPS ==================

def ensure_venv():
    print_header("🐍 VENV SETUP")
    if not VENV_DIR.exists():
        VENV_DIR.mkdir(parents=True, exist_ok=True)
        sh(["python3","-m","venv",str(VENV_DIR)])
    global PYTHON
    PYTHON = str(VENV_DIR / "bin/python")
    os.environ["PIP_ROOT_USER_ACTION"] = "ignore"
    sh([PYTHON,"-m","pip","install","-U","pip","setuptools","wheel"])

def install_dependencies():
    print_header("📦 INSTALLING DEPENDENCIES (pinned)")
    base_pkgs = [
        'huggingface-hub[hf_transfer]>=0.20.0',
        'vllm>=0.7.3,<0.9',
        'transformers>=4.46.1,<5',
        'mistral_common>=1.6.2',
        'compressed-tensors',
        'tokenizers',
        'sentencepiece',
        'tiktoken',
        'accelerate',
        'requests',
        'python-dotenv',  # Per leggere .env
    ]
    sh([PYTHON,"-m","pip","install","-U",*base_pkgs])
    sh([PYTHON,"-m","pip","install","--use-pep517","-U","autoawq>=0.2.0"])
    check_cuda()

# ================== MODEL I/O ==================

def download_model_and_tokenizer():
    print_header("📥 DOWNLOAD MODEL (AWQ/CT) + TOKENIZER (auto-fix)")
    ensure_dirs()
    os.environ["HF_HOME"] = str(HF_CACHE)
    os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "3600"

    py_code = f"""
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="{MODEL_REPO}",
    local_dir="{MODEL_PATH}",
    local_dir_use_symlinks=False,
    resume_download=True,
    max_workers=4,
    allow_patterns=[
        "*.safetensors","config.json","generation_config.json",
        "tokenizer.json","tokenizer.model","tokenizer_config.json","special_tokens_map.json",
        "*.tiktoken","*.txt","*.md"
    ]
)
print("OK")
"""
    sh([PYTHON,"-c",py_code], check=True, capture=True)

    missing = [f for f in REQUIRED_FILES if not (MODEL_PATH / f).exists()]
    has_any_tok = any((MODEL_PATH / f).exists() for f in REQUIRED_TOKENIZER_ANY)
    extra_missing = [f for f in REQUIRED_TOKENIZER_EXTRA if not (MODEL_PATH / f).exists()]
    if not has_any_tok:
        extra_missing = REQUIRED_TOKENIZER_ANY + REQUIRED_TOKENIZER_EXTRA

    if missing or extra_missing:
        print(f"ℹ️ Missing files: {missing + extra_missing} → pulling tokenizer from base repo")
        tk_tmp = MODEL_PATH / "_tokenizer_base"; tk_tmp.mkdir(parents=True, exist_ok=True)
        py_code2 = f"""
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="{TOKENIZER_BASE_REPO}",
    local_dir="{tk_tmp}",
    local_dir_use_symlinks=False,
    resume_download=True,
    max_workers=4,
    allow_patterns=["tokenizer.json","tokenizer.model","tokenizer_config.json","special_tokens_map.json","generation_config.json"]
)
print("OK")
"""
        sh([PYTHON,"-c",py_code2], check=True, capture=True)
        for fname in ["tokenizer.json","tokenizer.model","tokenizer_config.json","special_tokens_map.json","generation_config.json"]:
            src = tk_tmp / fname; dst = MODEL_PATH / fname
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst); print(f"   ➜ copied {fname}")

    print("✅ Model folder populated.")

def validate_model_folder():
    print_header("🧪 VALIDATE MODEL FOLDER")
    ok = True
    safes = list(MODEL_PATH.glob("*.safetensors"))
    print(f"Found {len(safes)} safetensors")
    if not safes: print("❌ No weights found"); ok=False
    for f in REQUIRED_FILES:
        if not (MODEL_PATH / f).exists(): print(f"❌ Missing {f}"); ok=False
    has_any_tok = any((MODEL_PATH / f).exists() for f in REQUIRED_TOKENIZER_ANY)
    if not has_any_tok: print("❌ Missing tokenizer.json or tokenizer.model"); ok=False
    for f in REQUIRED_TOKENIZER_EXTRA:
        if not (MODEL_PATH / f).exists(): print(f"⚠️ Missing (non-fatal) {f}")
    try:
        data = json.loads((MODEL_PATH / "config.json").read_text())
        q = (data.get("quantization_config") or {}).get("quant_method")
        if q: print(f"ℹ️ Detected quantization method: {q}")
    except Exception as e:
        print(f"⚠️ Cannot read quantization_config: {e}")
    if ok:
        sh(["du","-sh",str(MODEL_PATH)], check=False)
        print("✅ Model validation passed")
    return ok

def detect_quant_mode():
    cfg = MODEL_PATH / "config.json"
    try:
        data = json.loads(cfg.read_text())
        q = (data.get("quantization_config") or {}).get("quant_method")
        if q in ("awq","compressed-tensors"):
            print(f"🔎 Detected quantization method in config: {q}")
            return q
    except Exception:
        pass
    print("ℹ️ Falling back to 'compressed-tensors' (warshanks default)")
    return "compressed-tensors"

# =========== CHAT TEMPLATE ===========

def ensure_chat_template_file():
    """Scrive template robusto che gestisce content string/list/mapping"""
    tpl_path = MODEL_PATH / "mistral_chat_template.jinja"
    tpl = r"""{% macro norm(c) -%}
{%- if c is string -%}
{{ c }}
{%- elif c is mapping -%}
{{ c.get('text','') }}
{%- elif c is iterable and (c is not string) -%}
{%- for p in c -%}{%- if p is mapping and ('text' in p) -%}{{ p['text'] }}{%- endif -%}{%- endfor -%}
{%- else -%}
{{ c|string }}
{%- endif -%}
{%- endmacro %}

{%- set sys_text = "" -%}
{%- if messages and messages[0]['role'] == 'system' -%}
  {%- set sys_text = norm(messages[0]['content']) -%}
  {%- set messages = messages[1:] -%}
{%- endif -%}

{{ bos_token }}
{%- for m in messages %}
  {%- if m['role'] == 'user' -%}
    {%- set u = norm(m['content']) -%}
    {%- if loop.first -%}
      {{ "[INST] " ~ (sys_text ~ "\n" if sys_text else "") ~ u ~ " [/INST]" }}
    {%- else -%}
      {{ eos_token ~ " " ~ "[INST] " ~ u ~ " [/INST]" }}
    {%- endif -%}
  {%- elif m['role'] == 'assistant' -%}
    {%- set a = norm(m['content']) -%}
    {{ " " ~ a }}
  {%- else -%}
    {{ raise_exception("Only system (first), user and assistant roles are supported!") }}
  {%- endif -%}
{%- endfor -%}
{%- if add_generation_prompt -%} {{ " " }} {%- endif -%}
"""
    tpl_path.write_text(tpl, encoding="utf-8")
    print(f"📝 Wrote robust chat template → {tpl_path}")
    
    if not tpl_path.exists():
        raise RuntimeError(f"❌ Chat template file not created: {tpl_path}")
    
    return str(tpl_path)

def detect_kv_cache_dtype():
    """Auto-detect optimal KV cache dtype based on GPU architecture"""
    try:
        import torch
        major, minor = torch.cuda.get_device_capability(0)
        dtype = "fp8" if major >= 9 else "auto"
        print(f"🔍 GPU compute capability: {major}.{minor} → KV-cache dtype: {dtype}")
        return dtype
    except Exception as e:
        print(f"⚠️ Cannot detect GPU capability: {e}, using 'auto'")
        return "auto"

# ================== TUNNEL FUNCTIONS ==================

def setup_ssh_key():
    """Salva la chiave SSH dalla variabile d'ambiente"""
    print_header("🔑 SETUP SSH KEY")
    key_content = os.environ.get("GPU_SSH_PRIVATE_KEY", "").strip()
    
    if not key_content:
        print("⚠️  GPU_SSH_PRIVATE_KEY non trovata in .env")
        print("   Tunnel SSH non sarà configurato (fallback a connessione diretta)")
        return False
    
    if not key_content.startswith("-----BEGIN"):
        print("⚠️  GPU_SSH_PRIVATE_KEY formato invalido")
        return False
    
    GPU_KEY_PATH.parent.mkdir(parents=True, exist_ok=True)
    GPU_KEY_PATH.write_text(key_content, encoding="utf-8")
    os.chmod(GPU_KEY_PATH, 0o600)
    print(f"✅ Chiave SSH salvata in {GPU_KEY_PATH}")
    return True

def create_reverse_tunnel():
    """Crea reverse SSH tunnel: GPU:8001 → CPU:9001"""
    print_header("🔗 CREATE REVERSE TUNNEL")
    
    if not CPU_SSH_HOST:
        print("⚠️  CPU_SSH_HOST non configurato, skip tunnel")
        return False
    
    if not GPU_KEY_PATH.exists():
        print("❌ Chiave SSH mancante. Esegui setup_ssh_key() prima.")
        return False
    
    # Test connessione SSH
    print(f"🔍 Test connessione a {CPU_SSH_USER}@{CPU_SSH_HOST}:{CPU_SSH_PORT}")
    test_cmd = [
        "ssh", "-i", str(GPU_KEY_PATH),
        "-o", "StrictHostKeyChecking=no",
        "-o", "ConnectTimeout=10",
        "-o", "BatchMode=yes",
        f"{CPU_SSH_USER}@{CPU_SSH_HOST}",
        "-p", str(CPU_SSH_PORT),
        "echo 'SSH OK'"
    ]
    
    try:
        result = sh(test_cmd, capture=True, timeout=15, check=False)
        if result.returncode == 0:
            print("✅ SSH alla CPU funziona")
        else:
            print(f"❌ SSH test fallito: {result.stderr if result.stderr else 'timeout'}")
            return False
    except Exception as e:
        print(f"❌ Impossibile connettersi alla CPU: {e}")
        return False
    
    # Crea tunnel in background
    print(f"🚇 Creazione tunnel: GPU:{VLLM_PORT} → CPU:{CPU_TUNNEL_PORT}")
    tunnel_cmd = [
        "ssh", "-f", "-N",
        "-i", str(GPU_KEY_PATH),
        "-o", "StrictHostKeyChecking=no",
        "-o", "ServerAliveInterval=60",
        "-o", "ServerAliveCountMax=3",
        "-o", "ExitOnForwardFailure=yes",
        "-R", f"{CPU_TUNNEL_PORT}:127.0.0.1:{VLLM_PORT}",
        f"{CPU_SSH_USER}@{CPU_SSH_HOST}",
        "-p", str(CPU_SSH_PORT)
    ]
    
    try:
        sh(tunnel_cmd, timeout=10)
        print(f"✅ Reverse tunnel creato")
        time.sleep(2)
        return True
    except Exception as e:
        print(f"❌ Errore creazione tunnel: {e}")
        return False

def create_tunnel_service():
    """Crea servizio systemd per mantenere il tunnel attivo"""
    print_header("🔧 CREATE TUNNEL SERVICE")
    
    if not CPU_SSH_HOST or not GPU_KEY_PATH.exists():
        print("⚠️  Configurazione tunnel incompleta, skip servizio")
        return False
    
    service_content = f"""[Unit]
Description=Reverse SSH Tunnel to QuantumDev CPU
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=root
Restart=always
RestartSec=10
ExecStart=/usr/bin/ssh -N \\
  -i {GPU_KEY_PATH} \\
  -o StrictHostKeyChecking=no \\
  -o ServerAliveInterval=60 \\
  -o ServerAliveCountMax=3 \\
  -o ExitOnForwardFailure=yes \\
  -R {CPU_TUNNEL_PORT}:127.0.0.1:{VLLM_PORT} \\
  {CPU_SSH_USER}@{CPU_SSH_HOST} \\
  -p {CPU_SSH_PORT}

[Install]
WantedBy=multi-user.target
"""
    
    service_path = Path("/etc/systemd/system/gpu-reverse-tunnel.service")
    
    try:
        service_path.write_text(service_content)
        sh(["systemctl", "daemon-reload"], check=False)
        sh(["systemctl", "enable", "gpu-reverse-tunnel"], check=False)
        sh(["systemctl", "restart", "gpu-reverse-tunnel"], check=False)
        
        # Verifica stato
        time.sleep(2)
        result = sh(["systemctl", "is-active", "gpu-reverse-tunnel"], capture=True, check=False)
        if result.returncode == 0 and result.stdout.strip() == "active":
            print("✅ Servizio tunnel attivo e abilitato")
            return True
        else:
            print("⚠️  Servizio creato ma non attivo (verrà ritentato automaticamente)")
            return False
    except Exception as e:
        print(f"⚠️  Impossibile creare servizio systemd: {e}")
        print("   Il tunnel manuale funziona comunque")
        return False

# ================== RUNTIME (vLLM) ==================

def cleanup_gpu():
    print_header("🧹 CLEANUP OLD PROCESSES / SHM / PORT")
    sh(["pkill","-9","-f","vllm"], check=False)
    sh(["pkill","-9","-f","python.*api_server"], check=False)
    time.sleep(2)
    sh(["bash","-lc","rm -rf /dev/shm/torch_* /dev/shm/sem.torch*"], check=False)
    check_port_free()

def start_vllm():
    print_header("🚀 START vLLM (auto AWQ/CT)")
    env = env_base()
    env["VLLM_USE_FLASH_ATTN"] = "0"
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"

    qmode = detect_quant_mode()
    kvdtype = detect_kv_cache_dtype()
    chat_tpl = ensure_chat_template_file()

    cmd = [
        PYTHON, "-m", "vllm.entrypoints.openai.api_server",
        "--model", str(MODEL_PATH),
        "--tokenizer", str(MODEL_PATH),
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--quantization", qmode,
        "--dtype", "half",
        "--max-model-len", str(MAX_MODEL_LEN),
        "--tensor-parallel-size", "1",
        "--gpu-memory-utilization", str(GPU_MEMORY_UTIL),
        "--max-num-seqs", str(MAX_NUM_SEQS),
        "--disable-log-requests",
        "--trust-remote-code",
        "--enforce-eager",
        "--served-model-name", SERVED_MODEL_NAME,
        "--max-loras", "0",
        "--chat-template", chat_tpl,
        "--chat-template-content-format", "openai",
        "--kv-cache-dtype", kvdtype,
        "--swap-space", "16",
    ]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(" ".join(cmd))
    with open(LOG_PATH, "ab", buffering=0) as logf:
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=env)
    print(f"PID: {proc.pid}  |  log → {LOG_PATH}")
    return proc, qmode

def wait_ready(timeout=WAIT_TIMEOUT):
    print_header("⏳ WAITING FOR /v1/models")
    import requests
    url = f"http://127.0.0.1:{VLLM_PORT}/v1/models"
    t0 = time.time(); last_log = 0; spinner="|/-\\"; i=0
    while time.time()-t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.ok:
                ids = [m["id"] for m in r.json().get("data",[])]
                print(f"\n✅ READY. Models: {ids}"); return True
        except Exception:
            pass
        if time.time()-last_log > 25 and LOG_PATH.exists():
            try:
                with open(LOG_PATH,"r") as f: lines = f.readlines()[-18:]
                for ln in lines:
                    low = ln.lower()
                    if any(k in low for k in ["chat","template","tokenizer","awq","compressed","error","valueerror","missing","oom","cuda"]):
                        print("📋", ln.strip()[:180])
            except Exception: pass
            last_log = time.time()
        print(f"\r{spinner[i%4]} loading... {int(time.time()-t0)}s", end="", flush=True); i+=1
        time.sleep(2)
    print("\n⚠️ Timeout waiting for model")
    try: sh(["tail","-n","80",str(LOG_PATH)], check=False)
    except Exception: pass
    return False

def test_inference():
    print_header("🧪 TEST INFERENCE")
    import requests
    try:
        r = requests.get(f"http://127.0.0.1:{VLLM_PORT}/v1/models", timeout=5); r.raise_for_status()
        model_id = r.json()["data"][0]["id"]
    except Exception as e:
        print(f"❌ Cannot get model id: {e}"); return False

    payloads = [
        {"name":"Math (string)","messages":[{"role":"user","content":"What is 17*23? Reply with the number only."}], "max_tokens":8,"temp":0.0},
        {"name":"Explain (parts)","messages":[
            {"role":"system","content":[{"type":"text","text":"Be concise."}]},
            {"role":"user","content":[{"type":"text","text":"In one sentence, what is a Large Language Model?"}]}
        ], "max_tokens":40,"temp":0.2},
    ]
    ok=True
    for t in payloads:
        body = {"model": model_id, "messages": t["messages"], "temperature": t["temp"], "max_tokens": t["max_tokens"]}
        try:
            t0=time.time()
            r = requests.post(f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions", json=body, timeout=60)
            dt=time.time()-t0
            if r.ok:
                data = r.json(); txt = data["choices"][0]["message"]["content"].strip()
                ctoks = data.get("usage",{}).get("completion_tokens",0)
                print(f"✅ {t['name']}: {ctoks} toks in {dt:.1f}s → {txt[:80]}")
            else:
                print(f"❌ {t['name']} HTTP {r.status_code}: {r.text[:200]}"); ok=False
        except Exception as e:
            print(f"❌ {t['name']} exception: {e}"); ok=False
    return ok

def get_public_ip():
    import requests
    for u in ["http://checkip.amazonaws.com","http://ipecho.net/plain","http://icanhazip.com"]:
        try: return requests.get(u, timeout=5).text.strip()
        except Exception: pass
    return "127.0.0.1"

def register_backend(use_tunnel=False, qmode="compressed-tensors"):
    print_header("🔗 REGISTER BACKEND")
    import requests
    
    if use_tunnel:
        endpoint = f"http://127.0.0.1:{CPU_TUNNEL_PORT}/v1/chat/completions"
        print(f"📡 Registrando endpoint TUNNEL: {endpoint}")
    else:
        ip = get_public_ip()
        endpoint = f"http://{ip}:{VLLM_PORT}/v1/chat/completions"
        print(f"📡 Registrando endpoint DIRETTO: {endpoint}")
    
    payload = {
        "llm_endpoint": endpoint,
        "model": MODEL_ALIAS_INTERNAL,
        "gpu_config": "vast_rtx8000_48gb",
        "context_length": MAX_MODEL_LEN,
        "quantization": f"{qmode}-4bit",
        "location": "vast.ai",
        "tunnel_mode": use_tunnel
    }
    
    body = json.dumps(payload, separators=(",",":"))
    sig = hmac.new(QUANTUM_SHARED_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    hdr = {"Content-Type":"application/json","X-GPU-Signature":sig}
    
    try:
        r = requests.post(QUANTUM_BACKEND_API, data=body, headers=hdr, timeout=20)
        print(f"Status: {r.status_code}")
        if r.ok:
            print(f"✅ Backend registrato: {r.text[:200]}")
            return True
        else:
            print(f"⚠️  Registrazione fallita: {r.text[:200]}")
            return False
    except Exception as e:
        print(f"⚠️  Register error: {e}")
        return False

# ================== MAIN ==================

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="full",
                    choices=["check","deps","download","run","full","validate","test","setup-env"])
    args = ap.parse_args()

    # Setup .env se non esiste o se richiesto esplicitamente
    if args.action == "setup-env" or not ENV_PATH.exists():
        if not create_gpu_env_interactive():
            print("⚠️ Setup .env fallito, ma procedo comunque...")

    if args.action == "setup-env":
        print("✅ Setup .env completato.")
        sys.exit(0)

    if args.action == "check":
        sys.exit(0 if preflight() else 1)

    if args.action == "deps":
        ensure_venv(); install_dependencies(); check_cuda(); sys.exit(0)

    if args.action == "download":
        ensure_venv(); install_dependencies(); download_model_and_tokenizer()
        sys.exit(0 if validate_model_folder() else 1)

    if args.action == "validate":
        sys.exit(0 if validate_model_folder() else 1)

    if args.action == "run":
        cleanup_gpu()
        _, _ = start_vllm()
        sys.exit(0 if wait_ready() else 1)

    if args.action == "test":
        sys.exit(0 if test_inference() else 1)

    if args.action == "full":
        # Verifica/crea .env se manca
        if not ENV_PATH.exists():
            print("⚠️ File .env non trovato!")
            if not create_gpu_env_interactive():
                print("❌ Impossibile procedere senza .env")
                sys.exit(1)
        
        if not preflight(): sys.exit(1)
        ensure_venv(); install_dependencies(); download_model_and_tokenizer()
        if not validate_model_folder(): sys.exit(1)
        
        # === Setup SSH key e tunnel ===
        has_key = setup_ssh_key()
        tunnel_ok = False
        
        if has_key:
            tunnel_ok = create_reverse_tunnel()
            # Crea servizio anche se tunnel manuale fallisce (per auto-retry)
            create_tunnel_service()
        else:
            print("ℹ️  Tunnel non configurato, userò connessione diretta")
        
        # === Avvio vLLM ===
        cleanup_gpu()
        _, qmode = start_vllm()
        if not wait_ready(): sys.exit(1)
        tests_ok = test_inference()
        
        # === Registrazione backend ===
        register_ok = register_backend(use_tunnel=tunnel_ok, qmode=qmode)
        
        # === Report finale ===
        print_header("✅ ALL DONE")
        if tunnel_ok:
            print(f"🔗 Endpoint: http://CPU:{CPU_TUNNEL_PORT} (via tunnel)")
            print(f"   CPU: {CPU_SSH_HOST}")
        else:
            ip = get_public_ip()
            print(f"🌐 Endpoint: http://{ip}:{VLLM_PORT} (diretto)")
            if not register_ok:
                print("⚠️  Registrazione backend fallita, verifica logs")
        
        print(f"📊 Model: {SERVED_MODEL_NAME}")
        print(f"🔢 Quant: {qmode}-4bit")
        print(f"📏 Context: {MAX_MODEL_LEN} tokens")
        
        sys.exit(0 if (tests_ok and register_ok) else 1)

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted."); sys.exit(1)
