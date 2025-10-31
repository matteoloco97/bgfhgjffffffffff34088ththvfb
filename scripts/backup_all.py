import sys
import os

# Aggiunge la cartella principale al PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.wasabi_handler import upload_folder

# Percorso base del progetto
BASE_PATH = os.path.expanduser("~/quantumdev-open")

# Cartelle da salvare su Wasabi
FOLDERS_TO_BACKUP = {
    "config": "config/",
    "agents": "agents/",
    "memory": "memory/",
    "logs": "logs/"  # opzionale
}

def backup_all():
    print("\n📦 AVVIO BACKUP TOTALE SU WASABI...\n")

    for name, folder in FOLDERS_TO_BACKUP.items():
        full_path = os.path.join(BASE_PATH, folder)
        if os.path.exists(full_path):
            print(f"🔄 Backup {name.upper()}...")
            upload_folder(full_path, folder)
        else:
            print(f"⚠️ Cartella '{folder}' non trovata, skip...")

    print("\n✅ BACKUP COMPLETATO CON SUCCESSO\n")

if __name__ == "__main__":
    backup_all()
