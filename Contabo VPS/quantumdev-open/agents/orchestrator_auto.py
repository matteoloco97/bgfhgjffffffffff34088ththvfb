#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import json
import logging
import subprocess
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
import sys
import fcntl
from pathlib import Path
from typing import Dict

# === Config da ENV con fallback sensati ===
STATUS_FILE = Path(os.getenv("ORCH_STATUS_FILE", "/root/quantumdev-open/status/status.json"))
LOG_FILE    = Path(os.getenv("ORCH_LOG_FILE",    "/root/quantumdev-open/logs/orchestrator_auto.log"))
AGENTS_PATH = Path(os.getenv("ORCH_AGENTS_PATH", "/root/quantumdev-open/agents"))
LOCK_FILE   = Path(os.getenv("ORCH_LOCK_FILE",   "/tmp/quantum-orchestrator.lock"))

# Regole di scheduling (override via ORCH_RULES_JSON='{"agent": "1h", ...}')
DEFAULT_RULES = {
    "bootstrapper": "1h",
    "flush_cache": "6h",
    "chroma_bridge": "12h",
    "wasabi_agent": "1d",
    "backup": "4h",
}

def parse_duration(s: str) -> timedelta:
    s = s.strip().lower()
    if s.endswith("min"): return timedelta(minutes=int(s[:-3]))
    if s.endswith("m"):   return timedelta(minutes=int(s[:-1]))
    if s.endswith("h"):   return timedelta(hours=int(s[:-1]))
    if s.endswith("d"):   return timedelta(days=int(s[:-1]))
    # fallback: minuti interi
    return timedelta(minutes=int(s))

def load_rules() -> Dict[str, timedelta]:
    raw = os.getenv("ORCH_RULES_JSON")
    rules = DEFAULT_RULES if not raw else json.loads(raw)
    return {k: parse_duration(v) if isinstance(v, str) else timedelta(seconds=int(v)) for k, v in rules.items()}

RULES = load_rules()

# === Logging (rotazione) ===
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger("orchestrator_auto")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=5)
handler.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(handler)
# anche su stdout/stderr (journald)
console = logging.StreamHandler()
console.setFormatter(logging.Formatter("%(asctime)s - %(levelname)s - %(message)s"))
logger.addHandler(console)

logger.info("🤖 Avvio Orchestrator Auto")

# === Lock per evitare esecuzioni sovrapposte ===
LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
_lock_fd = open(LOCK_FILE, "w")
try:
    fcntl.flock(_lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    _lock_fd.write(str(os.getpid()))
    _lock_fd.flush()
except BlockingIOError:
    logger.warning("⛔ Orchestrator già in esecuzione (lock attivo). Esco.")
    sys.exit(0)

# === Stato persistente ===
def load_status() -> Dict[str, str]:
    if not STATUS_FILE.exists():
        return {}
    try:
        with open(STATUS_FILE, "r") as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"⚠️  Stato corrotto o illeggibile ({STATUS_FILE}): {e}. Riparto da vuoto.")
        return {}

def atomic_write(path: Path, data: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w") as f:
        f.write(data)
    os.replace(tmp, path)

def save_status(status: Dict[str, str]):
    atomic_write(STATUS_FILE, json.dumps(status, indent=2))

# === Schedule ===
def should_run(agent: str, last_run: str | None) -> bool:
    if agent not in RULES:
        return False
    try:
        last_dt = datetime.fromisoformat(last_run) if last_run else None
    except Exception:
        last_dt = None
    if not last_dt:
        return True
    return datetime.now() - last_dt > RULES[agent]

def agent_script_path(agent: str) -> Path:
    return AGENTS_PATH / f"{agent}.py"

def is_agent_running(agent: str) -> bool:
    """Evita doppioni: se c'è già un processo che sta girando per quel file, skip."""
    script = str(agent_script_path(agent))
    try:
        # pgrep ritorna 0 se trova match
        subprocess.run(["pgrep", "-f", script], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except subprocess.CalledProcessError:
        return False

def run_agent(agent: str) -> bool:
    script = agent_script_path(agent)
    if not script.exists():
        logger.warning(f"❌ Script mancante: {script}")
        return False
    if is_agent_running(agent):
        logger.info(f"⏳ '{agent}' già in esecuzione, salto il lancio.")
        return True  # consideriamo ok, non un errore

    try:
        # usa lo stesso interprete (venv) che sta eseguendo l’orchestrator
        python_bin = sys.executable
        subprocess.Popen(
            [python_bin, str(script)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            env=os.environ.copy(),
            cwd=str(AGENTS_PATH)
        )
        logger.info(f"🚀 Avviato agente '{agent}' → {script}")
        return True
    except Exception as e:
        logger.error(f"❌ Errore avvio {agent}: {e}")
        return False

def main():
    status = load_status()
    updated = False

    for agent in RULES:
        last_run = status.get(agent)
        if should_run(agent, last_run):
            logger.info(f"⏱️ Trigger agente: {agent}")
            if run_agent(agent):
                status[agent] = datetime.now().isoformat()
                updated = True
            else:
                logger.warning(f"⚠️ Fallito: {agent}")
        else:
            logger.info(f"⏭️ Skip agente: {agent}")

    if updated:
        save_status(status)
        logger.info("💾 Stato aggiornato.")
    else:
        logger.info("🔁 Nessun agente eseguito.")

if __name__ == "__main__":
    try:
        main()
    finally:
        try:
            fcntl.flock(_lock_fd, fcntl.LOCK_UN)
        except Exception:
            pass
