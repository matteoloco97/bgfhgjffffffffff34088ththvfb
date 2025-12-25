# agents/wasabi_agent.py

import os
import logging
import boto3
from dotenv import load_dotenv
from botocore.exceptions import ClientError

# === ENV ===
load_dotenv()

AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_DEFAULT_REGION")
BUCKET_NAME = os.getenv("AWS_BUCKET_NAME")

# === Logging ===
log_path = "/root/quantumdev-open/logs/wasabi_agent.log"
os.makedirs(os.path.dirname(log_path), exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler(log_path),
        logging.StreamHandler()
    ]
)

# === Avvio ===
logging.info("🚀 Avvio Wasabi Agent...")

# === Check parametri ===
if not all([AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, AWS_REGION, BUCKET_NAME]):
    logging.error("❌ Variabili .env mancanti o non caricate.")
    exit(1)

# === Client ===
try:
    s3 = boto3.client(
        "s3",
        endpoint_url=f"https://s3.{AWS_REGION}.wasabisys.com",
        aws_access_key_id=AWS_ACCESS_KEY_ID,
        aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
        region_name=AWS_REGION
    )

    # === Lista file ===
    logging.info(f"📦 Connessione al bucket: {BUCKET_NAME}")
    files = s3.list_objects_v2(Bucket=BUCKET_NAME)

    if "Contents" in files:
        logging.info("📁 File presenti su Wasabi:")
        for obj in files["Contents"]:
            logging.info(f" - {obj['Key']}")
    else:
        logging.info("📂 Nessun file presente nel bucket.")

except ClientError as e:
    logging.error(f"❌ Errore Wasabi: {e}")
