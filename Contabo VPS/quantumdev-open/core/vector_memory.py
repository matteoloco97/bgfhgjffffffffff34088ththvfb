#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/vector_memory.py — Vector Memory System for QuantumDev Max

Features:
- ChromaDB integration for semantic search
- Sentence transformer embeddings
- Session-based document storage
- Persistent vector database

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
CHROMA_PERSIST_DIR = os.getenv("CHROMA_PERSIST_DIR", "./data/chroma_db")
CHROMA_COLLECTION = os.getenv("CHROMA_COLLECTION", "quantumdev_memory")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "all-MiniLM-L6-v2")

# Global client and collection
_chroma_client = None
_collection = None
_embedding_function = None


def _get_embedding_function():
    """Get or create embedding function."""
    global _embedding_function
    if _embedding_function is None:
        try:
            from chromadb.utils import embedding_functions
            _embedding_function = embedding_functions.SentenceTransformerEmbeddingFunction(
                model_name=EMBEDDING_MODEL
            )
            log.info(f"Embedding function initialized: {EMBEDDING_MODEL}")
        except Exception as e:
            log.error(f"Failed to initialize embedding function: {e}")
            # Fallback to default
            import chromadb.utils.embedding_functions as ef
            _embedding_function = ef.DefaultEmbeddingFunction()
    return _embedding_function


def _get_chroma_client():
    """Get or create ChromaDB client."""
    global _chroma_client
    if _chroma_client is None:
        try:
            import chromadb
            
            # Create data directory if it doesn't exist
            os.makedirs(CHROMA_PERSIST_DIR, exist_ok=True)
            
            _chroma_client = chromadb.PersistentClient(path=CHROMA_PERSIST_DIR)
            log.info(f"ChromaDB client initialized at: {CHROMA_PERSIST_DIR}")
        except Exception as e:
            log.error(f"Failed to initialize ChromaDB client: {e}")
            raise
    return _chroma_client


def _get_collection():
    """Get or create ChromaDB collection."""
    global _collection
    if _collection is None:
        try:
            client = _get_chroma_client()
            embedding_fn = _get_embedding_function()
            
            _collection = client.get_or_create_collection(
                name=CHROMA_COLLECTION,
                embedding_function=embedding_fn,
                metadata={"description": "QuantumDev Max conversation memory"}
            )
            log.info(f"ChromaDB collection ready: {CHROMA_COLLECTION}")
        except Exception as e:
            log.error(f"Failed to get/create collection: {e}")
            raise
    return _collection


def add_document(
    session_id: str,
    text: str,
    metadata: Optional[Dict[str, Any]] = None
) -> bool:
    """
    Add a document to vector memory.
    
    Args:
        session_id: Session identifier
        text: Text content to store
        metadata: Optional metadata (must contain only string, int, float, or bool values)
        
    Returns:
        True if successful, False otherwise
    """
    if not text or not text.strip():
        log.warning("Cannot add empty document to vector memory")
        return False
    
    try:
        collection = _get_collection()
        
        # Generate unique ID
        import hashlib
        import time
        doc_id = hashlib.sha256(
            f"{session_id}:{text[:100]}:{time.time()}".encode()
        ).hexdigest()[:16]
        
        # Prepare metadata (ChromaDB requires specific types)
        doc_metadata = {
            "session_id": session_id,
            "timestamp": datetime.utcnow().isoformat(),
            "text_length": len(text),
        }
        
        # Add user metadata if provided (ensure proper types)
        if metadata:
            for key, value in metadata.items():
                # ChromaDB only accepts string, int, float, or bool
                if isinstance(value, (str, int, float, bool)):
                    doc_metadata[key] = value
                elif value is not None:
                    doc_metadata[key] = str(value)
        
        # Add to collection
        collection.add(
            documents=[text],
            metadatas=[doc_metadata],
            ids=[doc_id]
        )
        
        log.debug(f"Document added to vector memory: {doc_id}")
        return True
        
    except Exception as e:
        log.error(f"Failed to add document to vector memory: {e}")
        return False


def query_documents(
    session_id: str,
    query: str,
    top_k: int = 5
) -> List[Dict[str, Any]]:
    """
    Query documents from vector memory.
    
    Args:
        session_id: Session identifier to filter by
        query: Query text for semantic search
        top_k: Number of results to return
        
    Returns:
        List of documents with metadata and similarity scores
    """
    if not query or not query.strip():
        log.warning("Cannot query with empty text")
        return []
    
    try:
        collection = _get_collection()
        
        # Query with session filter
        results = collection.query(
            query_texts=[query],
            n_results=min(top_k, 100),  # Limit max results
            where={"session_id": session_id}
        )
        
        # Format results
        documents = []
        if results and results.get("documents") and results["documents"][0]:
            for i, doc_text in enumerate(results["documents"][0]):
                doc_data = {
                    "text": doc_text,
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else 0.0,
                }
                documents.append(doc_data)
        
        log.debug(f"Vector memory query returned {len(documents)} results")
        return documents
        
    except Exception as e:
        log.error(f"Failed to query vector memory: {e}")
        return []


def delete_session_documents(session_id: str) -> bool:
    """
    Delete all documents for a session.
    
    Args:
        session_id: Session identifier
        
    Returns:
        True if successful, False otherwise
    """
    try:
        collection = _get_collection()
        
        # Query all documents for this session
        results = collection.get(
            where={"session_id": session_id}
        )
        
        if results and results.get("ids"):
            collection.delete(ids=results["ids"])
            log.info(f"Deleted {len(results['ids'])} documents for session {session_id}")
            return True
        
        log.debug(f"No documents found for session {session_id}")
        return True
        
    except Exception as e:
        log.error(f"Failed to delete session documents: {e}")
        return False


def get_collection_stats() -> Dict[str, Any]:
    """
    Get statistics about the vector memory collection.
    
    Returns:
        Dictionary with collection statistics
    """
    try:
        collection = _get_collection()
        count = collection.count()
        
        return {
            "collection_name": CHROMA_COLLECTION,
            "document_count": count,
            "persist_dir": CHROMA_PERSIST_DIR,
            "embedding_model": EMBEDDING_MODEL,
        }
    except Exception as e:
        log.error(f"Failed to get collection stats: {e}")
        return {
            "collection_name": CHROMA_COLLECTION,
            "error": str(e)
        }
