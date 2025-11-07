import boto3
import os
import logging
import json
from datetime import datetime
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# === LOAD ENV ===
load_dotenv()

# === CONFIG ===
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
BUCKET_NAME = "quantum-memory"
LOCAL_ROOT = "/root/quantumdev-open/"
FILES_TO_BACKUP = [
    "config/settings.yaml",
    ".env",
    "agents/agents_snapshot.json"
]
FOLDERS_TO_BACKUP = [
    "memory/chroma",
    "agents"
]

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def upload_file(s3, local_path, s3_key):
    try:
        s3.upload_file(local_path, BUCKET_NAME, s3_key)
        logger.info(f"✅ File caricato: {s3_key}")
    except ClientError as e:
        logger.error(f"❌ Errore upload {s3_key}: {e}")

def backup_folder(s3, folder):
    for root, _, files in os.walk(os.path.join(LOCAL_ROOT, folder)):
        for file in files:
            local_path = os.path.join(root, file)
            rel_path = os.path.relpath(local_path, LOCAL_ROOT)
            upload_file(s3, local_path, rel_path)

def generate_agents_snapshot():
    snapshot = []
    agents_path = os.path.join(LOCAL_ROOT, "agents")

    for filename in os.listdir(agents_path):
        full_path = os.path.join(agents_path, filename)
        if filename.endswith(".py") and os.path.isfile(full_path):
            snapshot.append({
                "agent": filename,
                "path": f"agents/{filename}",
                "last_modified": datetime.fromtimestamp(os.path.getmtime(full_path)).isoformat(),
                "status": "attivo"
            })

    output_path = os.path.join(agents_path, "agents_snapshot.json")
    with open(output_path, "w") as f:
        json.dump(snapshot, f, indent=2)

    logger.info(f"📝 Snapshot agenti generato: {output_path}")

def main():
    logger.info("☁ Avvio Backup Agent...")

    try:
        s3 = boto3.client("s3",
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            endpoint_url="https://s3.eu-central-2.wasabisys.com"
        )
    except Exception as e:
        logger.error(f"❌ Errore creazione client S3: {e}")
        return

    # === Genera snapshot agenti ===
    generate_agents_snapshot()

    # === Backup file singoli ===
    for file in FILES_TO_BACKUP:
        local_path = os.path.join(LOCAL_ROOT, file)
        if os.path.exists(local_path):
            upload_file(s3, local_path, file)
        else:
            logger.warning(f"⚠️ File mancante: {file}")

    # === Backup cartelle ===
    for folder in FOLDERS_TO_BACKUP:
        backup_folder(s3, folder)

    logger.info("🔚 Backup completato.")

if __name__ == "__main__":
    main()
