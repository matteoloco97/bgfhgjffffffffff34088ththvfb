# agents/chroma_bridge.py

import os
import logging
import uuid

from dotenv import load_dotenv
from chromadb import PersistentClient
from sentence_transformers import SentenceTransformer

# === Load .env ===
load_dotenv()

# === Config Logging ===
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# === Setup Chroma ===
CHROMA_PATH = os.getenv("CHROMA_PATH", "memory/chroma")
COLLECTION_NAME = "memory"

client = PersistentClient(path=CHROMA_PATH)
collection = client.get_or_create_collection(name=COLLECTION_NAME)
model = SentenceTransformer("all-MiniLM-L6-v2")

# === Funzioni ===
def add_to_chroma(text):
    embedding = model.encode(text).tolist()
    doc_id = str(uuid.uuid4())
    collection.add(documents=[text], embeddings=[embedding], ids=[doc_id])
    logger.info(f"✅ Aggiunto in memoria: {text[:50]}...")
    return doc_id

def query_chroma(query_text, top_k=3):
    query_embedding = model.encode(query_text).tolist()
    results = collection.query(query_embeddings=[query_embedding], n_results=top_k)
    return results

# === Esecuzione test ===
if __name__ == "__main__":
    logger.info("🧠 Avvio ChromaBridge Agent...")

    test_text = "QuantumBet è un assistente per il betting sportivo."
    add_to_chroma(test_text)

    query = "Cos'è QuantumBet?"
    result = query_chroma(query)

    logger.info("🔍 Risultati simili trovati:")
    for doc in result["documents"][0]:
        logger.info(f"→ {doc}")
