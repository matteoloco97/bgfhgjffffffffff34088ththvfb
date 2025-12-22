#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_cpu_tunnel.py - CPU Tunnel Setup for QuantumDev
Configura la CPU per ricevere reverse tunnel SSH dalla GPU.

Usage:
  sudo python3 setup_cpu_tunnel.py [--port 9011] [--user gpu-tunnel]
                                   [--key-name gpu_key]
                                   [--env-path /root/quantumdev-open/.env]
                                   [--regenerate-key] [--no-env-patch]
"""

import os
import sys
import re
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Tuple

# ========= CONFIG =========

DEFAULT_TUNNEL_USER = "gpu-tunnel"
DEFAULT_TUNNEL_PORT = 9011   # <-- PATCH default porta 9011
DEFAULT_KEY_NAME    = "gpu_key"
DEFAULT_ENV_PATH    = "/root/quantumdev-open/.env"

# ========= Helpers =========

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

def log(msg: str, level: str = "INFO"):
    prefix = {
        "INFO":    f"{Colors.BLUE}ℹ️ {Colors.END}",
        "SUCCESS": f"{Colors.GREEN}✅{Colors.END}",
        "WARNING": f"{Colors.YELLOW}⚠️ {Colors.END}",
        "ERROR":   f"{Colors.RED}❌{Colors.END}",
    }.get(level, "")
    print(f"{prefix} {msg}")

def section(title: str):
    print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{title}{Colors.END}")
    print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")

def run_cmd(cmd: list, check: bool = True, capture: bool = False) -> Tuple[int, str, str]:
    try:
        result = subprocess.run(
            cmd, check=check, capture_output=capture, text=True
        )
        return result.returncode, result.stdout if capture else "", result.stderr if capture else ""
    except subprocess.CalledProcessError as e:
        if check:
            raise
        return e.returncode, e.stdout if capture else "", e.stderr if capture else ""

def check_root():
    if os.geteuid() != 0:
        log("Questo script deve essere eseguito come root!", "ERROR")
        log("Usa: sudo python3 setup_cpu_tunnel.py", "INFO")
        sys.exit(1)

# ========= Core =========

def create_user(username: str) -> bool:
    log(f"Verifico utente '{username}'...")
    ret, _, _ = run_cmd(["id", username], check=False, capture=True)
    if ret == 0:
        log(f"Utente '{username}' già esistente", "INFO")
        return True
    log(f"Creazione utente '{username}'...", "INFO")
    try:
        run_cmd(["useradd", "-m", "-s", "/bin/bash", username])
        log(f"Utente '{username}' creato", "SUCCESS")
        return True
    except subprocess.CalledProcessError as e:
        log(f"Errore creazione utente: {e}", "ERROR")
        return False

def setup_ssh_directory(username: str) -> Optional[Path]:
    log("Setup directory SSH...")
    user_home = Path(f"/home/{username}")
    ssh_dir = user_home / ".ssh"
    try:
        ssh_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
        run_cmd(["chown", "-R", f"{username}:{username}", str(user_home)])
        log(f"Directory SSH: {ssh_dir}", "SUCCESS")
        return ssh_dir
    except Exception as e:
        log(f"Errore setup SSH directory: {e}", "ERROR")
        return None

def generate_ssh_key(ssh_dir: Path, key_name: str, regenerate: bool) -> Optional[Path]:
    """Genera chiave ed25519 (non interattivo). Se esiste e non --regenerate-key, la riusa."""
    log("Gestione chiave SSH (ed25519)...")
    key_path = ssh_dir / key_name
    pub_path = ssh_dir / (key_name + ".pub")

    if key_path.exists() and pub_path.exists() and not regenerate:
        log("Chiave esistente: verrà riutilizzata (usa --regenerate-key per rigenerare).", "INFO")
        return key_path

    # Rigenera
    if key_path.exists():
        key_path.unlink(missing_ok=True)
    if pub_path.exists():
        pub_path.unlink(missing_ok=True)

    try:
        run_cmd([
            "ssh-keygen", "-t", "ed25519",
            "-f", str(key_path),
            "-N", "",
            "-C", f"gpu-tunnel@quantumdev"
        ])
        run_cmd(["chown", f"{ssh_dir.parent.name}:{ssh_dir.parent.name}", str(key_path)])
        run_cmd(["chown", f"{ssh_dir.parent.name}:{ssh_dir.parent.name}", str(pub_path)])
        log(f"Chiave generata: {key_path}", "SUCCESS")
        return key_path
    except subprocess.CalledProcessError as e:
        log(f"Errore generazione chiave: {e}", "ERROR")
        return None

def setup_authorized_keys(ssh_dir: Path, key_path: Path, username: str) -> bool:
    log("Configurazione authorized_keys...")
    try:
        pub_key_path = Path(str(key_path) + ".pub")
        authorized_keys = ssh_dir / "authorized_keys"

        with open(pub_key_path, 'r') as f:
            pub_key = f.read().strip()

        with open(authorized_keys, 'w') as f:
            f.write(pub_key + '\n')

        os.chmod(authorized_keys, 0o600)
        run_cmd(["chown", f"{username}:{username}", str(authorized_keys)])
        log("authorized_keys configurato", "SUCCESS")
        return True
    except Exception as e:
        log(f"Errore configurazione authorized_keys: {e}", "ERROR")
        return False

def _ensure_sshd_option(config: str, key: str, value: str) -> Tuple[str, bool]:
    """
    Assicura/imposta 'key value' in sshd_config (gestisce override idempotente).
    Se la chiave esiste non commentata, la sostituisce; altrimenti la aggiunge.
    """
    pattern = re.compile(rf"^\s*{re.escape(key)}\s+.+$", re.MULTILINE)
    line = f"{key} {value}"
    if pattern.search(config):
        new_config = pattern.sub(line, config)
        return new_config, (new_config != config)
    else:
        if not config.endswith("\n"):
            config += "\n"
        new_config = config + f"# QuantumDev Tunnel Settings\n{line}\n"
        return new_config, True

def configure_sshd(username: str, port: int) -> bool:
    log("Configurazione SSHD per il reverse tunneling...")
    sshd_config = Path("/etc/ssh/sshd_config")
    backup_config = Path("/etc/ssh/sshd_config.backup.quantumdev")

    try:
        # Backup
        if not backup_config.exists():
            run_cmd(["cp", str(sshd_config), str(backup_config)])
            log(f"Backup config: {backup_config}", "INFO")

        with open(sshd_config, 'r') as f:
            config = f.read()

        changed = False
        for key, value in {
            "AllowTcpForwarding": "yes",
            "GatewayPorts": "no",
            "PermitTunnel": "yes",
        }.items():
            config, did = _ensure_sshd_option(config, key, value)
            changed = changed or did

        # (Opzionale) Limitare l'utente e la porta con Match User + PermitOpen
        # È sicuro lasciar perdere per flessibilità. Se vuoi restringere:
        # match_block = f"\nMatch User {username}\n    PermitOpen 127.0.0.1:{port}\n"
        # if "Match User" not in config:
        #     config += match_block
        #     changed = True

        if changed:
            with open(sshd_config, 'w') as f:
                f.write(config)
            log("Config SSHD aggiornata", "SUCCESS")
        else:
            log("Config SSHD già corretta", "INFO")

        run_cmd(["systemctl", "restart", "sshd"])
        log("SSHD riavviato", "SUCCESS")
        return True
    except Exception as e:
        log(f"Errore configurazione SSHD: {e}", "ERROR")
        return False

def save_keys_for_gpu(key_path: Path, config_dir: Path):
    log("Salvataggio copia chiavi in repo per GPU...")
    try:
        config_dir.mkdir(parents=True, exist_ok=True)
        gpu_private_key = config_dir / "gpu_private_key"
        gpu_public_key = config_dir / "gpu_public_key.pub"
        run_cmd(["cp", str(key_path), str(gpu_private_key)])
        run_cmd(["cp", f"{key_path}.pub", str(gpu_public_key)])
        os.chmod(gpu_private_key, 0o600)
        log(f"Chiavi salvate in: {config_dir}", "SUCCESS")
    except Exception as e:
        log(f"Errore salvataggio chiavi: {e}", "WARNING")

def print_private_key(key_path: Path):
    section("CHIAVE PRIVATA PER GPU")
    print(f"{Colors.YELLOW}⚠️  IMPORTANTE: Copia questa chiave sulla GPU{Colors.END}\n")
    print(f"{Colors.BOLD}--- INIZIO CHIAVE ---{Colors.END}")
    with open(key_path, 'r') as f:
        print(f.read())
    print(f"{Colors.BOLD}--- FINE CHIAVE ---{Colors.END}\n")

def verify_setup(username: str, ssh_dir: Path) -> bool:
    section("VERIFICA SETUP")
    checks = {
        f"User {username}": lambda: run_cmd(["id", username], check=False, capture=True)[0] == 0,
        "SSH directory":   lambda: ssh_dir.exists() and os.access(ssh_dir, os.R_OK),
        "authorized_keys": lambda: (ssh_dir / "authorized_keys").exists(),
        "SSHD running":    lambda: run_cmd(["systemctl", "is-active", "sshd"], check=False, capture=True)[1].strip() == "active",
    }
    all_ok = True
    for name, fn in checks.items():
        ok = fn()
        log(f"{name}: {'✅' if ok else '❌'}", "SUCCESS" if ok else "ERROR")
        all_ok = all_ok and ok
    return all_ok

def patch_env_file(env_path: Path, port: int) -> bool:
    """Aggiorna .env: LLM_ENDPOINT e TUNNEL_ENDPOINT → http://127.0.0.1:{port}/v1"""
    try:
        if not env_path.exists():
            log(f".env non trovato in {env_path} (salto patch).", "WARNING")
            return False

        with open(env_path, "r") as f:
            lines = f.read().splitlines()

        def set_kv(lines, key, value):
            pat = re.compile(rf"^\s*{re.escape(key)}\s*=")
            out = []
            found = False
            for ln in lines:
                if pat.match(ln):
                    out.append(f"{key}={value}")
                    found = True
                else:
                    out.append(ln)
            if not found:
                out.append(f"{key}={value}")
            return out

        endpoint = f"http://127.0.0.1:{port}/v1"
        lines = set_kv(lines, "LLM_ENDPOINT", endpoint)
        lines = set_kv(lines, "TUNNEL_ENDPOINT", endpoint)

        with open(env_path, "w") as f:
            f.write("\n".join(lines) + "\n")

        log(f".env patchato: LLM_ENDPOINT/TUNNEL_ENDPOINT → {endpoint}", "SUCCESS")
        return True
    except Exception as e:
        log(f"Errore patch .env: {e}", "ERROR")
        return False

def restart_quantum_api():
    """Riavvia quantum-api.service se presente"""
    ret, out, _ = run_cmd(["systemctl", "list-unit-files", "quantum-api.service"], check=False, capture=True)
    if ret == 0 and "quantum-api.service" in out:
        run_cmd(["systemctl", "daemon-reload"], check=False)
        run_cmd(["systemctl", "restart", "quantum-api.service"], check=False)
        log("quantum-api.service riavviato", "SUCCESS")
    else:
        log("quantum-api.service non trovato (ok se non usi systemd per l'API).", "WARNING")

# ========= Main =========

def main():
    parser = argparse.ArgumentParser(description="Setup CPU per reverse tunnel GPU")
    parser.add_argument("--user", default=DEFAULT_TUNNEL_USER, help="Tunnel username")
    parser.add_argument("--port", type=int, default=DEFAULT_TUNNEL_PORT, help="Tunnel port (bind su 127.0.0.1)")
    parser.add_argument("--key-name", default=DEFAULT_KEY_NAME, help="Nome file chiave in ~/.ssh")
    parser.add_argument("--env-path", default=DEFAULT_ENV_PATH, help="Path .env da patchare")
    parser.add_argument("--regenerate-key", action="store_true", help="Rigenera la chiave anche se esiste")
    parser.add_argument("--no-env-patch", action="store_true", help="Non patchare il file .env")
    args = parser.parse_args()

    check_root()

    section("🔧 QUANTUMDEV - CPU TUNNEL SETUP")
    log(f"User : {args.user}", "INFO")
    log(f"Port : {args.port}", "INFO")
    log(f".env : {args.env_path}", "INFO")

    if not create_user(args.user):
        sys.exit(1)

    ssh_dir = setup_ssh_directory(args.user)
    if not ssh_dir:
        sys.exit(1)

    key_path = generate_ssh_key(ssh_dir, args.key_name, regenerate=args.regenerate_key)
    if not key_path:
        sys.exit(1)

    if not setup_authorized_keys(ssh_dir, key_path, args.user):
        sys.exit(1)

    if not configure_sshd(args.user, args.port):
        sys.exit(1)

    # Salva copia chiavi in repo
    config_dir = Path.cwd() / "config" / "gpu-tunnel"
    save_keys_for_gpu(key_path, config_dir)

    # Patch .env e riavvio servizi
    if not args.no_env_patch:
        patched = patch_env_file(Path(args.env_path), args.port)
        if patched:
            restart_quantum_api()

    ok = verify_setup(args.user, ssh_dir)
    if not ok:
        log("Setup completato con avvertimenti", "WARNING")
    else:
        section("✅ SETUP COMPLETATO CON SUCCESSO!")

    # Stampa chiave privata da copiare sulla GPU
    print_private_key(key_path)

    section("📋 PROSSIMI PASSI")
    print(f"1) Copia la chiave privata sopra sulla GPU in /workspace/.ssh/gpu_tunnel")
    print(f"2) Sulla GPU: chmod 600 /workspace/.ssh/gpu_tunnel")
    print(f"3) Sulla GPU esporta variabili o .env e avvia il tunnel sulla porta {args.port}")
    print(f"   (es.) CPU_TUNNEL_PORT={args.port}")
    print(f"\n{Colors.GREEN}🎉 CPU pronta a ricevere il reverse tunnel su 127.0.0.1:{args.port}{Colors.END}\n")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{Colors.YELLOW}⚠️  Operazione interrotta{Colors.END}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{Colors.RED}❌ Errore fatale: {e}{Colors.END}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
