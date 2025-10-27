#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_gpu.py — QuantumDev GPU bootstrap (robust + self-healing)

Fix principali inclusi:
- Chat template Jinja robusto (gestisce content str/list)
- Rimozione flag non supportati (niente --kv-cache-dtype fp16)
- Avvio conservativo per evitare OOM + fallback automatici
- Mitigazione frammentazione: PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

Azioni:
  - check     → preflight (GPU/disk/port)
  - deps      → crea/aggiorna venv + installa dipendenze
  - download  → scarica modello + tokenizer (auto-fix)
  - validate  → valida cartella modello
  - run       → avvia vLLM con profilo conservativo
  - test      → test rapido chat/completions
  - full      → check + deps + download + validate + run (con fallback) + test + register
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

# ================== GLOBAL CONFIG ==================

# Percorsi
WORKSPACE = Path(os.environ.get("WORKSPACE_DIR", "/workspace"))
VENV_DIR = Path(os.environ.get("VENV_DIR", "/venv/main"))
MODELS_DIR = WORKSPACE / "models"
MODEL_PATH = Path(os.environ.get("MODEL_PATH", str(MODELS_DIR / "dolphin-24b-venice-awq")))
HF_CACHE = Path(os.environ.get("HF_CACHE", str(WORKSPACE / "hf_cache")))
LOG_PATH = WORKSPACE / "vllm_dolphin24b.log"

# Python/venv
PYTHON = str(VENV_DIR / "bin/python") if VENV_DIR.exists() else "python3"
PIP = f"{PYTHON} -m pip"

# Modello
MODEL_REPO = os.environ.get("MODEL_REPO", "warshanks/Dolphin-Mistral-24B-Venice-Edition-AWQ")
TOKENIZER_BASE_REPO = os.environ.get("TOKENIZER_BASE_REPO", "mistralai/Mistral-Small-24B-Instruct-2501")

MODEL_ALIAS_INTERNAL = os.environ.get("MODEL_ALIAS_INTERNAL", "dolphin-24b-venice")
SERVED_MODEL_NAME = os.environ.get("SERVED_MODEL_NAME", "llama-3.1-70b")

# Server
VLLM_PORT = int(os.environ.get("VLLM_PORT", "8001"))
WAIT_TIMEOUT = int(os.environ.get("WAIT_TIMEOUT", "1800"))  # 30 min

# Parametri conservativi iniziali (profili di avvio)
BASE_PROFILES = [
    # (max_model_len, max_num_seqs, gpu_memory_util)
    (3072, 1, 0.80),
    (2048, 1, 0.75),
    (1536, 1, 0.70),
]

# Backend registration (HMAC)
QUANTUM_BACKEND_API = os.environ.get("QUANTUM_BACKEND_API", "http://84.247.166.247:8081/update_gpu")
QUANTUM_SHARED_SECRET = os.environ.get(
    "QUANTUM_SHARED_SECRET",
    "5e6ad9f7c2b14dceb2f4a1a9087c3da0d4a885c3e85f1b2d47a6f0e9c3b21d77"
)

# ================== UTILS ==================

def sh(cmd, check=True, capture=False, env=None, timeout=None):
    """Esegue un comando shell con logging leggibile."""
    if isinstance(cmd, str):
        shell = True
        printable = cmd
    else:
        shell = False
        printable = " ".join(str(c) for c in cmd)
    print(f"\n💻 $ {printable}")
    try:
        if capture:
            res = subprocess.run(cmd, check=check, capture_output=True, text=True,
                                 env=env, timeout=timeout, shell=shell)
            if res.stdout:
                print(res.stdout.strip())
            if res.stderr and (not check):
                print(res.stderr.strip())
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

def print_header(title):
    print("\n" + "="*80)
    print(title)
    print("="*80)

def ensure_dirs():
    HF_CACHE.mkdir(parents=True, exist_ok=True)
    MODEL_PATH.mkdir(parents=True, exist_ok=True)

def env_base():
    env = os.environ.copy()
    env["HF_HOME"] = str(HF_CACHE)
    env["HF_HUB_ENABLE_HF_TRANSFER"] = "1"
    env["HF_HUB_DOWNLOAD_TIMEOUT"] = "3600"
    env["CUDA_VISIBLE_DEVICES"] = env.get("CUDA_VISIBLE_DEVICES", "0")
    # anti-frammentazione CUDA
    env["PYTORCH_CUDA_ALLOC_CONF"] = "expandable_segments:True"
    return env

# ================== PREFLIGHT ==================

def check_gpu():
    print_header("🔍 GPU CHECK")
    try:
        res = sh(["nvidia-smi", "--query-gpu=index,name,memory.total", "--format=csv,noheader,nounits"],
                 capture=True)
        line = res.stdout.strip().splitlines()[0]
        idx, name, total_mb = [x.strip() for x in line.split(",")]
        total_gb = int(total_mb) / 1024
        print(f"GPU {idx}: {name}  |  VRAM: {total_gb:.1f} GB")
        if total_gb < 24:
            print("❌ Need ≥ 24GB for 24B@INT4 with 8K context.")
            return False
        print("✅ GPU OK")
        return True
    except Exception as e:
        print(f"❌ Cannot read GPU info: {e}")
        return False

def check_disk():
    print_header("💾 DISK CHECK (/workspace)")
    try:
        res = sh(["df", "-h", str(WORKSPACE)], capture=True)
        lines = res.stdout.strip().splitlines()
        print("\n".join(lines))
        parts = lines[1].split()
        avail = parts[3]
        num = float(avail[:-1]); unit = avail[-1]
        avail_gb = num * (1024 if unit.upper()=="T" else 1)
        need_gb = 26 + 12  # pesi + buffer
        if avail_gb < need_gb:
            print(f"❌ Low space. Need ≥ ~{need_gb} GB free.")
            return False
        print("✅ Disk OK")
        return True
    except Exception as e:
        print(f"⚠️ Disk check error: {e}")
        return True

def check_port_free():
    print_header(f"🔌 PORT CHECK (tcp:{VLLM_PORT})")
    out = sh(["bash","-lc", f"if command -v lsof >/dev/null; then lsof -i TCP:{VLLM_PORT} -sTCP:LISTEN || true; fi"],
             capture=True, check=False)
    if out and out.stdout and "LISTEN" in out.stdout:
        print("⚠️ Port busy. Killing old vLLM.")
        try:
            sh(["pkill", "-9", "-f", "vllm"], check=False)
        except Exception:
            pass
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
        sh(["python3", "-m", "venv", str(VENV_DIR)])
    global PYTHON, PIP
    PYTHON = str(VENV_DIR / "bin/python")
    PIP = f"{PYTHON} -m pip"
    os.environ["PIP_ROOT_USER_ACTION"] = "ignore"
    sh([PYTHON, "-m", "pip", "install", "-U", "pip", "setuptools", "wheel"])

def check_cuda():
    print_header("🔍 CUDA / PyTorch CHECK")
    code = (
        "import torch, json; "
        "print(json.dumps({'torch': torch.__version__, 'cuda': torch.version.cuda, 'is_cuda': torch.cuda.is_available()}))"
    )
    try:
        res = sh([PYTHON, "-c", code], capture=True)
        info = json.loads(res.stdout.strip())
        print(f"PyTorch: {info['torch']} | CUDA: {info['cuda']} | GPU available: {info['is_cuda']}")
        if not info["is_cuda"]:
            print("❌ PyTorch does not see the GPU")
            return False
        print("✅ CUDA OK")
        return True
    except Exception as e:
        print(f"❌ CUDA/PyTorch check failed: {e}")
        return False

def install_dependencies():
    print_header("📦 INSTALLING DEPENDENCIES (pinned)")
    base_pkgs = [
        'huggingface-hub[hf_transfer]>=0.20.0',
        'vllm>=0.7.3,<0.9',
        'transformers>=4.46.1,<5',
        'mistral_common>=1.6.2',
        'compressed-tensors>=0.6',
        'tokenizers',
        'sentencepiece',
        'tiktoken',
        'accelerate',
        'requests',
        'jinja2',
    ]
    sh([PYTHON, "-m", "pip", "install", "-U", *base_pkgs])
    # opzionale, non critico
    sh([PYTHON, "-m", "pip", "install", "--use-pep517", "-U", "autoawq>=0.2.0"], check=False)
    check_cuda()

# ================== MODEL DOWNLOAD & VALIDATION ==================

REQUIRED_FILES = ["config.json", "generation_config.json"]
REQUIRED_TOKENIZER_ANY = ["tokenizer.json", "tokenizer.model"]
REQUIRED_TOKENIZER_EXTRA = ["tokenizer_config.json", "special_tokens_map.json"]

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
        "*.safetensors",
        "config.json",
        "generation_config.json",
        "tokenizer.json",
        "tokenizer.model",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "*.tiktoken",
        "*.txt",
        "*.md"
    ]
)
print("OK")
"""
    sh([PYTHON, "-c", py_code], check=True, capture=True)

    # se mancano file di tokenizer, prende dal base repo
    missing = [f for f in REQUIRED_FILES if not (MODEL_PATH / f).exists()]
    has_any_tok = any((MODEL_PATH / f).exists() for f in REQUIRED_TOKENIZER_ANY)
    extra_missing = [f for f in REQUIRED_TOKENIZER_EXTRA if not (MODEL_PATH / f).exists()]
    if not has_any_tok:
        extra_missing = REQUIRED_TOKENIZER_ANY + REQUIRED_TOKENIZER_EXTRA

    if missing or extra_missing:
        print(f"ℹ️ Missing files: {missing + extra_missing} → pulling tokenizer from base repo")
        tk_tmp = MODEL_PATH / "_tokenizer_base"
        tk_tmp.mkdir(parents=True, exist_ok=True)
        py_code2 = f"""
from huggingface_hub import snapshot_download
snapshot_download(
    repo_id="{TOKENIZER_BASE_REPO}",
    local_dir="{tk_tmp}",
    local_dir_use_symlinks=False,
    resume_download=True,
    max_workers=4,
    allow_patterns=[
        "tokenizer.json",
        "tokenizer.model",
        "tokenizer_config.json",
        "special_tokens_map.json",
        "generation_config.json"
    ]
)
print("OK")
"""
        sh([PYTHON, "-c", py_code2], check=True, capture=True)
        for fname in ["tokenizer.json","tokenizer.model","tokenizer_config.json",
                      "special_tokens_map.json","generation_config.json"]:
            src = tk_tmp / fname
            dst = MODEL_PATH / fname
            if src.exists() and not dst.exists():
                shutil.copy2(src, dst)
                print(f"   ➜ copied {fname}")

    print("✅ Model folder populated.")

def validate_model_folder():
    print_header("🧪 VALIDATE MODEL FOLDER")
    ok = True
    safes = list(MODEL_PATH.glob("*.safetensors"))
    print(f"Found {len(safes)} safetensors")
    if not safes:
        print("❌ No weights found"); ok=False
    for f in REQUIRED_FILES:
        if not (MODEL_PATH / f).exists():
            print(f"❌ Missing {f}"); ok=False
    has_any_tok = any((MODEL_PATH / f).exists() for f in REQUIRED_TOKENIZER_ANY)
    if not has_any_tok:
        print("❌ Missing tokenizer.json or tokenizer.model"); ok=False
    for f in REQUIRED_TOKENIZER_EXTRA:
        if not (MODEL_PATH / f).exists():
            print(f"⚠️ Missing (non-fatal) {f}")
    try:
        data = json.loads((MODEL_PATH / "config.json").read_text())
        q = (data.get("quantization_config") or {}).get("quant_method")
        if q:
            print(f"ℹ️ Detected quantization method: {q}")
    except Exception as e:
        print(f"⚠️ Cannot read quantization_config: {e}")

    if ok:
        sh(["du", "-sh", str(MODEL_PATH)], check=False)
        print("✅ Model validation passed")
    return ok

def detect_quant_mode():
    cfg = MODEL_PATH / "config.json"
    try:
        data = json.loads(cfg.read_text())
        q = (data.get("quantization_config") or {}).get("quant_method")
        if q in ("awq", "compressed-tensors"):
            print(f"🔎 Detected quantization method in config: {q}")
            return q
    except Exception as e:
        print(f"⚠️ Cannot read quantization_config: {e}")
    print("ℹ️ Falling back to 'awq'")
    return "awq"

# ================== CHAT TEMPLATE ==================

def ensure_chat_template_file():
    """
    Scrive un template Jinja robusto per Mistral se mancante.
    Se in tokenizer_config.json è presente chat_template, lo usa.
    """
    tk_cfg = MODEL_PATH / "tokenizer_config.json"
    tpl_path = MODEL_PATH / "mistral_chat_template.jinja"

    # tenta estrazione da tokenizer_config.json
    try:
        if tk_cfg.exists():
            data = json.loads(tk_cfg.read_text())
            tpl_val = data.get("chat_template")
            if isinstance(tpl_val, str) and len(tpl_val.strip()) > 0:
                tpl_path.write_text(tpl_val, encoding="utf-8")
                print(f"📝 Extracted chat template from tokenizer_config.json → {tpl_path}")
                return str(tpl_path)
    except Exception as e:
        print(f"⚠️ Could not read tokenizer_config.json chat_template: {e}")

    # fallback robusto che normalizza stringhe/liste
    tpl = r"""{% macro norm(c) -%}
{%- if c is string -%}{{ c }}
{%- elif c is mapping -%}{{ c.get('text','') }}
{%- elif c is iterable and (c is not string) -%}
{%- for p in c -%}{%- if p is mapping and ('text' in p) -%}{{ p['text'] }}{%- endif -%}{%- endfor -%}
{%- else -%}{{ c|string }}
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
    {{ " " ~ norm(m['content']) }}
  {%- else -%}
    {{ raise_exception("Only system (first), user and assistant roles are supported!") }}
  {%- endif -%}
{%- endfor -%}
{%- if add_generation_prompt -%} {{ " " }} {%- endif -%}
"""
    tpl_path.write_text(tpl, encoding="utf-8")
    print(f"📝 Wrote robust fallback chat template → {tpl_path}")
    return str(tpl_path)

# ================== RUNTIME (vLLM) ==================

def cleanup_gpu():
    print_header("🧹 CLEANUP OLD PROCESSES / SHM / PORT")
    sh(["pkill", "-9", "-f", "vllm"], check=False)
    sh(["pkill", "-9", "-f", "python.*api_server"], check=False)
    time.sleep(2)
    sh(["bash","-lc","rm -rf /dev/shm/torch_* /dev/shm/sem.torch*"], check=False)
    check_port_free()

def start_vllm(max_model_len, max_num_seqs, gpu_mem_util):
    print_header(f"🚀 START vLLM (len={max_model_len}, seqs={max_num_seqs}, util={gpu_mem_util})")
    env = env_base()
    env["VLLM_USE_FLASH_ATTN"] = "0"  # conservativo per RTX 6000 Ada/RTX 8000
    qmode = detect_quant_mode()
    chat_tpl = ensure_chat_template_file()

    cmd = [
        PYTHON, "-m", "vllm.entrypoints.openai.api_server",
        "--model", str(MODEL_PATH),
        "--tokenizer", str(MODEL_PATH),
        "--host", "0.0.0.0",
        "--port", str(VLLM_PORT),
        "--quantization", qmode,
        "--dtype", "half",
        "--max-model-len", str(max_model_len),
        "--tensor-parallel-size", "1",
        "--gpu-memory-utilization", str(gpu_mem_util),
        "--max-num-seqs", str(max_num_seqs),
        "--disable-log-requests",
        "--trust-remote-code",
        "--enforce-eager",
        "--served-model-name", SERVED_MODEL_NAME,
        "--max-loras", "0",
        "--chat-template", chat_tpl,
        "--chat-template-content-format", "openai",
        "--swap-space", "16",
    ]
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    print(" ".join(cmd))
    with open(LOG_PATH, "ab", buffering=0) as logf:
        proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, env=env)
    print(f"PID: {proc.pid}  |  log → {LOG_PATH}")
    return proc, qmode

def _log_contains(patterns):
    """Controlla se il log contiene una delle pattern."""
    try:
        with open(LOG_PATH, "r", encoding="utf-8", errors="ignore") as f:
            tail = f.readlines()[-200:]
        low = "\n".join(tail).lower()
        return any(p in low for p in patterns)
    except Exception:
        return False

def wait_ready(timeout=WAIT_TIMEOUT):
    print_header("⏳ WAITING FOR /v1/models")
    import requests
    url = f"http://127.0.0.1:{VLLM_PORT}/v1/models"
    t0 = time.time()
    last_log = 0
    spinner = "|/-\\"
    i = 0
    while time.time()-t0 < timeout:
        try:
            r = requests.get(url, timeout=3)
            if r.ok:
                data = r.json()
                ids = [m["id"] for m in data.get("data",[])]
                print(f"✅ READY. Models: {ids}")
                return True, "ok"
        except Exception:
            pass

        # segnali d'errore nel log
        if _log_contains(["outofmemoryerror", "cuda out of memory", "engine core initialization failed"]):
            print("\n⚠️ Detected OOM/engine init failure in log")
            return False, "oom"

        if time.time()-last_log > 25 and LOG_PATH.exists():
            try:
                with open(LOG_PATH,"r", encoding="utf-8", errors="ignore") as f:
                    lines = f.readlines()[-18:]
                for ln in lines:
                    low = ln.lower()
                    if any(k in low for k in ["tokenizer","awq","compressed","safetensors","error","valueerror","missing","oom"]):
                        print("📋", ln.strip()[:180])
            except Exception:
                pass
            last_log = time.time()
        print(f"\r{spinner[i%4]} loading... {int(time.time()-t0)}s", end="", flush=True); i+=1
        time.sleep(2)

    print("\n⚠️ Timeout waiting for model")
    return False, "timeout"

def test_inference():
    print_header("🧪 TEST INFERENCE")
    import requests
    try:
        r = requests.get(f"http://127.0.0.1:{VLLM_PORT}/v1/models", timeout=5)
        r.raise_for_status()
        model_id = r.json()["data"][0]["id"]
    except Exception as e:
        print(f"❌ Cannot get model id: {e}")
        return False

    payloads = [
        {"name":"Math","prompt":"What is 17*23? Reply with the number only.","max_tokens":8,"temp":0},
        {"name":"Explain","prompt":"In one sentence, what is a Large Language Model?","max_tokens":40,"temp":0.2},
    ]
    ok=True
    for t in payloads:
        body = {"model": model_id,
                "messages":[{"role":"user","content":t["prompt"]}],
                "temperature": t["temp"],
                "max_tokens": t["max_tokens"]}
        try:
            t0=time.time()
            r = requests.post(f"http://127.0.0.1:{VLLM_PORT}/v1/chat/completions", json=body, timeout=60)
            dt=time.time()-t0
            if r.ok:
                data = r.json()
                txt = data["choices"][0]["message"]["content"].strip()
                ctoks = data.get("usage",{}).get("completion_tokens",0)
                print(f"✅ {t['name']}: {ctoks} toks in {dt:.1f}s → {txt[:80]}")
            else:
                print(f"❌ {t['name']} HTTP {r.status_code}: {r.text[:200]}")
                ok=False
        except Exception as e:
            print(f"❌ {t['name']} exception: {e}")
            ok=False
    return ok

def get_public_ip():
    import requests
    for u in ["http://checkip.amazonaws.com","http://ipecho.net/plain","http://icanhazip.com"]:
        try:
            return requests.get(u, timeout=5).text.strip()
        except Exception:
            pass
    return "127.0.0.1"

def register_backend(ip, qmode):
    print_header("🔗 REGISTER BACKEND")
    import requests
    payload = {
        "llm_endpoint": f"http://{ip}:{VLLM_PORT}/v1/chat/completions",
        "model": MODEL_ALIAS_INTERNAL,
        "gpu_config": "rtx_8000_45gb",
        "context_length": BASE_PROFILES[0][0],
        "quantization": f"{qmode}-4bit",
        "location": "usa"
    }
    body = json.dumps(payload, separators=(",",":"))
    sig = hmac.new(QUANTUM_SHARED_SECRET.encode(), body.encode(), hashlib.sha256).hexdigest()
    hdr = {"Content-Type":"application/json","X-GPU-Signature":sig}
    try:
        r = requests.post(QUANTUM_BACKEND_API, data=body, headers=hdr, timeout=20)
        print("Status:", r.status_code, r.text[:200])
    except Exception as e:
        print("⚠️ Register failed:", e)

# ================== MAIN ==================

def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("action", nargs="?", default="full",
                    choices=["check","deps","download","run","full","validate","test"])
    args = ap.parse_args()

    if args.action == "check":
        ok = preflight()
        sys.exit(0 if ok else 1)

    if args.action == "deps":
        ensure_venv(); install_dependencies()
        check_cuda()
        sys.exit(0)

    if args.action == "download":
        ensure_venv(); install_dependencies()
        download_model_and_tokenizer()
        ok = validate_model_folder()
        sys.exit(0 if ok else 1)

    if args.action == "validate":
        ok = validate_model_folder()
        sys.exit(0 if ok else 1)

    if args.action == "run":
        cleanup_gpu()
        # prova i profili in ordine finché non parte
        for (m_len, m_seqs, g_util) in BASE_PROFILES:
            proc, qmode = start_vLLM_and_wait(m_len, m_seqs, g_util)
            if proc is not None:
                sys.exit(0)
        sys.exit(1)

    if args.action == "test":
        ok = test_inference()
        sys.exit(0 if ok else 1)

    # full pipeline
    if args.action == "full":
        ok = preflight()
        if not ok: sys.exit(1)
        ensure_venv()
        install_dependencies()
        download_model_and_tokenizer()
        if not validate_model_folder(): sys.exit(1)

        cleanup_gpu()
        proc = None
        qmode = "awq"
        # tenta profili conservativi con fallback automatico
        for (m_len, m_seqs, g_util) in BASE_PROFILES:
            proc, qmode = start_vLLM_and_wait(m_len, m_seqs, g_util)
            if proc is not None:
                break
        if proc is None:
            sys.exit(1)

        tests_ok = test_inference()
        ip = get_public_ip()
        print(f"🌐 Public IP: {ip}")
        register_backend(ip, qmode)
        print_header("✅ ALL DONE")
        print(f"Endpoint  : http://{ip}:{VLLM_PORT}")
        print(f"Model name: {SERVED_MODEL_NAME} (served-model-name)")
        print(f"Quant     : {qmode}-4bit")
        sys.exit(0 if tests_ok else 1)

def start_vLLM_and_wait(m_len, m_seqs, g_util):
    """Helper: avvia vLLM con i parametri indicati e attende readiness con fallback su OOM."""
    cleanup_gpu()
    proc, qmode = start_vllm(m_len, m_seqs, g_util)
    ready, reason = wait_ready(timeout=WAIT_TIMEOUT)
    if ready:
        return proc, qmode
    # se fallisce, kill e prova prossimo profilo
    try:
        proc.terminate()
    except Exception:
        pass
    print(f"❌ Start failed (reason: {reason}). Trying next profile...")
    return None, qmode

if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.")
        sys.exit(1)
