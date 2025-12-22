import boto3
import os
import logging
from botocore.exceptions import NoCredentialsError, ClientError
from dotenv import load_dotenv

# === CARICA .env ===
load_dotenv()

# === CONFIG ===
BUCKET_NAME = "quantum-capitol"
LOCAL_ROOT = "/root/quantumdev-open/"
FILES_TO_RESTORE = [
    "config/settings.yaml",
    ".env",
]
FOLDERS_TO_RESTORE = [
    "memory/chroma",
    "agents"
]

# === LOGGING ===
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

def restore_file(s3, key, local_path):
    os.makedirs(os.path.dirname(local_path), exist_ok=True)
    try:
        s3.download_file(BUCKET_NAME, key, local_path)
        logger.info(f"✅ File ripristinato: {key}")
    except ClientError as e:
        logger.error(f"❌ Errore nel download {key}: {e}")

def restore_folder(s3, prefix, local_folder):
    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=BUCKET_NAME, Prefix=prefix):
        for obj in page.get("Contents", []):
            rel_path = obj["Key"]
            local_path = os.path.join(LOCAL_ROOT, rel_path)
            restore_file(s3, rel_path, local_path)

def main():
    logger.info("📦 Avvio Restore Agent...")

    try:
        session = boto3.Session(
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY")
        )
        s3 = session.client("s3")
    except NoCredentialsError:
        logger.error("❌ Credenziali AWS mancanti.")
        return

    # Ripristina file singoli
    for file in FILES_TO_RESTORE:
        local_path = os.path.join(LOCAL_ROOT, file)
        if not os.path.exists(local_path):
            restore_file(s3, file, local_path)
        else:
            logger.info(f"⏭️ Già presente: {file}")

    # Ripristina cartelle
    for folder in FOLDERS_TO_RESTORE:
        local_path = os.path.join(LOCAL_ROOT, folder)
        if not os.path.exists(local_path):
            restore_folder(s3, folder, local_path)
        else:
            logger.info(f"⏭️ Già presente: {folder}/")

    logger.info("🔚 Restore completato.")

if __name__ == "__main__":
    main()
