import sys
import os

# Aggiunge la cartella principale al PYTHONPATH
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.wasabi_handler import download_folder

# Percorso base del progetto
BASE_PATH = os.path.expanduser("~/quantumdev-open")

# Cartelle da ripristinare da Wasabi
FOLDERS_TO_RESTORE = {
    "config": "config/",
    "agents": "agents/",
    "memory": "memory/",
    "logs": "logs/"
}

def restore_all():
    print("\n🔁 AVVIO RIPRISTINO TOTALE DA WASABI...\n")

    for name, folder in FOLDERS_TO_RESTORE.items():
        local_path = os.path.join(BASE_PATH, folder)
        print(f"📥 Ripristino {name.upper()}...")
        download_folder(folder, local_path)

    print("\n✅ RIPRISTINO COMPLETATO CON SUCCESSO\n")

if __name__ == "__main__":
    restore_all()
