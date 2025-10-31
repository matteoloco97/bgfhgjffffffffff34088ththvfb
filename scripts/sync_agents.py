import sys
import os
import json

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from utils.wasabi_handler import upload_file, download_file

BASE_PATH = os.path.expanduser("~/quantumdev-open")

# Percorso locale e remoto
AGENTS_FILE = os.path.join(BASE_PATH, "agents", "agents_snapshot.json")
REMOTE_KEY = "agents/agents_snapshot.json"

def save_agents_snapshot(agent_data):
    os.makedirs(os.path.dirname(AGENTS_FILE), exist_ok=True)
    with open(AGENTS_FILE, "w") as f:
        json.dump(agent_data, f, indent=2)
    upload_file(AGENTS_FILE, REMOTE_KEY)
    print("✅ Agenti salvati su Wasabi.")

def load_agents_snapshot():
    os.makedirs(os.path.dirname(AGENTS_FILE), exist_ok=True)
    download_file(REMOTE_KEY, AGENTS_FILE)
    with open(AGENTS_FILE) as f:
        data = json.load(f)
    print("✅ Agenti caricati dal backup.")
    return data

if __name__ == "__main__":
    # ESEMPIO USO MANUALE
    example_agents = {
        "Scraper": {"status": "active", "version": "1.0"},
        "Deploy": {"status": "idle", "version": "1.0"}
    }

    save_agents_snapshot(example_agents)
    data = load_agents_snapshot()
    print(data)
