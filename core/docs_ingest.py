#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/docs_ingest.py — Document Ingestion & RAG for QuantumDev

Features:
- Extract text from files (txt, markdown, PDF)
- Intelligent text chunking
- ChromaDB indexing for document retrieval
- Query user documents with semantic search

Author: QuantumDev (BLOCK 4)
Version: 1.0.0
"""

from __future__ import annotations

import os
import sys
import io
import re
import time
import logging
from typing import List, Dict, Any, Optional
from pathlib import Path

# Ensure project root is in path
ROOT = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# PDF support
try:
    import PyPDF2
    HAS_PDF = True
except ImportError:
    HAS_PDF = False

# ChromaDB integration
from utils.chroma_handler import get_client, _embedder

log = logging.getLogger(__name__)

# === Configuration ===
USER_DOCS_COLLECTION = os.getenv("CHROMA_COLLECTION_USER_DOCS", "user_docs")
DEFAULT_CHUNK_SIZE = int(os.getenv("DOCS_CHUNK_SIZE", "1000"))
DEFAULT_CHUNK_OVERLAP = int(os.getenv("DOCS_CHUNK_OVERLAP", "200"))


def extract_text_from_file(path: str, mime_type: str) -> str:
    """
    Extract text content from a file.
    
    Args:
        path: Path to the file
        mime_type: MIME type of the file (e.g., 'text/plain', 'application/pdf')
        
    Returns:
        Extracted text as string
        
    Raises:
        ValueError: If file type is not supported
    """
    # Normalize mime type
    mime_lower = mime_type.lower()
    
    # Plain text files
    if 'text/plain' in mime_lower or path.endswith('.txt'):
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return f.read()
        except UnicodeDecodeError:
            # Try with Latin-1 encoding as fallback
            with open(path, 'r', encoding='latin-1') as f:
                return f.read()
    
    # Markdown files
    if 'text/markdown' in mime_lower or path.endswith('.md'):
        with open(path, 'r', encoding='utf-8') as f:
            return f.read()
    
    # PDF files
    if 'application/pdf' in mime_lower or path.endswith('.pdf'):
        if not HAS_PDF:
            raise ValueError("PDF support not available. Install PyPDF2.")
        
        try:
            with open(path, 'rb') as f:
                pdf_reader = PyPDF2.PdfReader(f)
                text_parts = []
                
                for page_num in range(len(pdf_reader.pages)):
                    page = pdf_reader.pages[page_num]
                    text = page.extract_text()
                    if text:
                        text_parts.append(text)
                
                return '\n'.join(text_parts)
        except Exception as e:
            log.error(f"PDF extraction failed: {e}")
            raise ValueError(f"Failed to extract PDF: {e}")
    
    # Unsupported type
    raise ValueError(f"Unsupported file type: {mime_type}")


def extract_text_from_bytes(content: bytes, mime_type: str, filename: str = "document") -> str:
    """
    Extract text content from bytes (for in-memory processing).
    
    Args:
        content: File content as bytes
        mime_type: MIME type of the file
        filename: Original filename (for extension detection)
        
    Returns:
        Extracted text as string
        
    Raises:
        ValueError: If file type is not supported
    """
    mime_lower = mime_type.lower()
    
    # Plain text
    if 'text/plain' in mime_lower or filename.endswith('.txt'):
        try:
            return content.decode('utf-8')
        except UnicodeDecodeError:
            return content.decode('latin-1')
    
    # Markdown
    if 'text/markdown' in mime_lower or filename.endswith('.md'):
        return content.decode('utf-8')
    
    # PDF
    if 'application/pdf' in mime_lower or filename.endswith('.pdf'):
        if not HAS_PDF:
            raise ValueError("PDF support not available. Install PyPDF2.")
        
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(content))
            text_parts = []
            
            for page_num in range(len(pdf_reader.pages)):
                page = pdf_reader.pages[page_num]
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            
            return '\n'.join(text_parts)
        except Exception as e:
            log.error(f"PDF extraction from bytes failed: {e}")
            raise ValueError(f"Failed to extract PDF: {e}")
    
    raise ValueError(f"Unsupported file type: {mime_type}")


def chunk_text(
    text: str,
    max_chars: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP
) -> List[str]:
    """
    Split text into manageable chunks with overlap.
    Preserves paragraph and sentence boundaries where possible.
    
    Args:
        text: Text to chunk
        max_chars: Maximum characters per chunk
        overlap: Overlap between chunks (in characters)
        
    Returns:
        List of text chunks
    """
    if not text or not text.strip():
        return []
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # If text is small enough, return as single chunk
    if len(text) <= max_chars:
        return [text]
    
    chunks = []
    
    # Split by paragraphs first
    paragraphs = re.split(r'\n\n+', text)
    
    current_chunk = ""
    
    for para in paragraphs:
        para = para.strip()
        if not para:
            continue
        
        # If adding this paragraph exceeds max_chars
        if len(current_chunk) + len(para) + 1 > max_chars:
            # Save current chunk if not empty
            if current_chunk:
                chunks.append(current_chunk)
                
                # Start new chunk with overlap from previous
                if overlap > 0 and len(current_chunk) > overlap:
                    current_chunk = current_chunk[-overlap:] + " " + para
                else:
                    current_chunk = para
            else:
                # Paragraph is too long, need to split by sentences
                sentences = re.split(r'(?<=[.!?])\s+', para)
                
                for sent in sentences:
                    if len(current_chunk) + len(sent) + 1 > max_chars:
                        if current_chunk:
                            chunks.append(current_chunk)
                            if overlap > 0 and len(current_chunk) > overlap:
                                current_chunk = current_chunk[-overlap:] + " " + sent
                            else:
                                current_chunk = sent
                        else:
                            # Even single sentence is too long, force split
                            current_chunk = sent[:max_chars]
                            chunks.append(current_chunk)
                            current_chunk = sent[max_chars:]
                    else:
                        current_chunk = (current_chunk + " " + sent).strip()
        else:
            current_chunk = (current_chunk + " " + para).strip()
    
    # Add remaining chunk
    if current_chunk:
        chunks.append(current_chunk)
    
    return chunks


def index_document(
    user_id: str,
    file_id: str,
    filename: str,
    text: str,
    max_chunks: Optional[int] = None
) -> Dict[str, Any]:
    """
    Index a document in ChromaDB for retrieval.
    
    Args:
        user_id: User identifier
        file_id: Unique file identifier
        filename: Original filename
        text: Extracted text content
        max_chunks: Maximum number of chunks to store (None for no limit)
        
    Returns:
        Dictionary with indexing results
    """
    try:
        # Chunk the text
        chunks = chunk_text(text)
        
        if not chunks:
            return {
                "ok": False,
                "error": "no_content_to_index",
                "num_chunks": 0,
            }
        
        # Track if chunks were truncated
        total_chunks = len(chunks)
        truncated = False
        
        # Apply max_chunks limit if specified
        if max_chunks and len(chunks) > max_chunks:
            log.warning(f"Document has {len(chunks)} chunks, limiting to {max_chunks}")
            chunks = chunks[:max_chunks]
            truncated = True
        
        # Get ChromaDB collection
        client = get_client()
        collection = client.get_or_create_collection(
            name=USER_DOCS_COLLECTION,
            metadata={"schema": "type=user_doc;fields=user_id,file_id,filename,chunk_index,created_at"},
            embedding_function=_embedder()
        )
        
        # Prepare data for insertion
        ids = []
        documents = []
        metadatas = []
        
        created_at = int(time.time())
        
        for idx, chunk in enumerate(chunks):
            chunk_id = f"doc:{file_id}:{idx}"
            ids.append(chunk_id)
            documents.append(chunk)
            metadatas.append({
                "user_id": user_id,
                "file_id": file_id,
                "filename": filename,
                "chunk_index": idx,
                "created_at": created_at,
            })
        
        # Upsert into ChromaDB
        collection.upsert(
            ids=ids,
            documents=documents,
            metadatas=metadatas
        )
        
        log.info(f"Indexed {len(chunks)} chunks for file {file_id} (user {user_id})")
        
        result = {
            "ok": True,
            "num_chunks": len(chunks),
            "file_id": file_id,
            "filename": filename,
        }
        
        # Add truncation info if applicable
        if truncated:
            result["truncated"] = True
            result["total_chunks"] = total_chunks
        
        return result
        
    except Exception as e:
        log.error(f"Document indexing failed: {e}")
        return {
            "ok": False,
            "error": str(e),
            "num_chunks": 0,
        }


def query_user_docs(
    user_id: str,
    query: str,
    top_k: int = 5,
    file_id: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query user documents using semantic search.
    
    Args:
        user_id: User identifier
        query: Search query
        top_k: Number of results to return
        file_id: Optional filter by specific file
        
    Returns:
        List of matching document chunks with metadata
    """
    try:
        client = get_client()
        
        # Check if collection exists
        try:
            collection = client.get_collection(
                name=USER_DOCS_COLLECTION,
                embedding_function=_embedder()
            )
        except Exception:
            log.warning(f"Collection {USER_DOCS_COLLECTION} not found")
            return []
        
        # Build where filter
        where_filter = {"user_id": user_id}
        if file_id:
            where_filter["file_id"] = file_id
        
        # Query ChromaDB
        results = collection.query(
            query_texts=[query],
            n_results=top_k,
            where=where_filter
        )
        
        # Format results
        matches = []
        
        if results and results.get("documents"):
            documents = results["documents"][0]
            metadatas = results.get("metadatas", [[]])[0]
            distances = results.get("distances", [[]])[0]
            
            for i, doc in enumerate(documents):
                metadata = metadatas[i] if i < len(metadatas) else {}
                distance = distances[i] if i < len(distances) else 1.0
                
                # Convert distance to similarity score (lower distance = higher similarity)
                score = 1.0 - min(distance, 1.0)
                
                matches.append({
                    "text": doc,
                    "file_id": metadata.get("file_id", ""),
                    "filename": metadata.get("filename", ""),
                    "chunk_index": metadata.get("chunk_index", 0),
                    "score": round(score, 4),
                })
        
        return matches
        
    except Exception as e:
        log.error(f"Document query failed: {e}")
        return []


# === Test ===
if __name__ == "__main__":
    print("🗂️  Document Ingestion Module - Test Suite\n")
    print("=" * 70)
    
    # Test chunking
    test_text = """
    This is a test document with multiple paragraphs.
    Each paragraph should be handled properly.
    
    Here is the second paragraph. It contains some information
    that should be chunked appropriately based on the max_chars setting.
    
    And here is a third paragraph with even more content to ensure
    that the chunking algorithm works correctly across different lengths.
    """
    
    chunks = chunk_text(test_text, max_chars=100, overlap=20)
    print(f"✅ Chunking test: {len(chunks)} chunks created")
    for i, chunk in enumerate(chunks):
        print(f"   Chunk {i}: {len(chunk)} chars - {chunk[:50]}...")
    
    print("\n" + "=" * 70)
    print("🎉 Document Ingestion Module - Ready")
