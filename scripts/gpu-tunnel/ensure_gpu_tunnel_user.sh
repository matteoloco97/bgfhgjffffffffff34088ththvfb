#!/usr/bin/env bash
set -euo pipefail
USER_NAME="gpu-tunnel"
SSH_DIR="/home/${USER_NAME}/.ssh"
AUTH_KEYS="${SSH_DIR}/authorized_keys"

# 1) Crea utente se manca
if ! id -u "${USER_NAME}" >/dev/null 2>&1; then
  sudo useradd -m -s /bin/bash "${USER_NAME}"
fi

sudo mkdir -p "${SSH_DIR}"
sudo touch "${AUTH_KEYS}"
sudo chmod 700 "${SSH_DIR}"
sudo chmod 600 "${AUTH_KEYS}"
sudo chown -R "${USER_NAME}:${USER_NAME}" "${SSH_DIR}"

echo "✅ Utente e cartelle OK: ${USER_NAME}"

echo "ℹ️  Per aggiungere la pubkey della GPU:"
echo "    echo 'ssh-ed25519 AAAA... vast-gpu' | sudo tee -a ${AUTH_KEYS} >/dev/null && sudo chown ${USER_NAME}:${USER_NAME} ${AUTH_KEYS}"
echo "    sudo chmod 600 ${AUTH_KEYS}"
