from chromadb import PersistentClient
import os

chroma_path = os.path.expanduser("~/quantumdev-open/memory/chroma")

client = PersistentClient(path=chroma_path)

# === FUNZIONI BASE ===

def add_to_collection(collection_name, ids, documents, metadatas=None):
    collection = client.get_or_create_collection(collection_name)
    collection.add(documents=documents, ids=ids, metadatas=metadatas)
    print(f"✅ Aggiunti {len(ids)} documenti alla collezione '{collection_name}'.")

def query_collection(collection_name, query_texts, n_results=1):
    collection = client.get_collection(collection_name)
    result = collection.query(query_texts=query_texts, n_results=n_results)
    return result

def list_collections():
    return [col.name for col in client.list_collections()]
