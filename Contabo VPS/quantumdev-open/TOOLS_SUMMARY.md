# BLOCK 4: Advanced Tools - Implementation Summary

## Overview

This document describes the implementation of BLOCK 4 Advanced Tools for the QuantumDev system, including:
1. **Math/Calculator Tool** - Safe mathematical expression evaluation
2. **Python Code Executor** - Sandboxed Python code execution  
3. **File Ingestion + Document RAG** - Upload and semantic search over user documents

## 1. Math/Calculator Tool

### Module: `core/calculator.py`

A professional-grade calculator with financial precision (28 decimal places).

**Features:**
- Basic arithmetic: +, -, *, /, %, **
- Functions: sqrt, pow, exp, log, log10, log2, sin, cos, tan, abs, round, floor, ceil, factorial
- Constants: pi, e, tau
- Security: Blocks dangerous patterns (import, eval, exec, etc.)
- Precision: Decimal-based for financial accuracy

### API Endpoint: `POST /tools/math`

**Request:**
```json
{
  "expr": "sqrt(16) + pow(2, 3)"
}
```

**Response:**
```json
{
  "ok": true,
  "result": "12",
  "type": "exact",
  "expr": "sqrt(16) + pow(2, 3)"
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/tools/math \
  -H "Content-Type: application/json" \
  -d '{"expr": "2+2*3"}'
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_MATH_ENABLED` | `true` | Enable/disable math tool |

### Examples

```bash
# Basic arithmetic
curl -X POST http://localhost:8000/tools/math \
  -H "Content-Type: application/json" \
  -d '{"expr": "2+2"}'

# Trigonometry
curl -X POST http://localhost:8000/tools/math \
  -H "Content-Type: application/json" \
  -d '{"expr": "sin(pi/2)"}'

# Financial calculation
curl -X POST http://localhost:8000/tools/math \
  -H "Content-Type: application/json" \
  -d '{"expr": "100*(1+0.05)**10"}'
```

---

## 2. Python Code Executor

### Module: `agents/code_execution.py`

Executes Python code in a sandboxed subprocess with strict security controls.

**Security Features:**
- Timeout enforcement (default 3s, configurable)
- Blocks dangerous imports: os, subprocess, sys, socket, etc.
- Blocks dangerous builtins: eval, exec, compile, open, etc.
- Input length limit (10KB max)
- Isolated subprocess execution

### API Endpoint: `POST /tools/python`

**Request:**
```json
{
  "code": "result = 5 + 3 * 2\nprint(f'Result: {result}')",
  "timeout_s": 5.0
}
```

**Response:**
```json
{
  "ok": true,
  "stdout": "Result: 11\n",
  "stderr": "",
  "error": null,
  "timeout": false
}
```

**cURL Example:**
```bash
curl -X POST http://localhost:8000/tools/python \
  -H "Content-Type: application/json" \
  -d '{"code": "print(\"Hello, World!\")"}'
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_PYTHON_EXEC_ENABLED` | `false` | Enable/disable Python executor (⚠️ disabled by default for security) |
| `CODE_EXEC_TIMEOUT` | `10` | Execution timeout in seconds |

### Examples

```bash
# Simple calculation
curl -X POST http://localhost:8000/tools/python \
  -H "Content-Type: application/json" \
  -d '{"code": "x = 10\ny = 20\nprint(x + y)"}'

# Data processing
curl -X POST http://localhost:8000/tools/python \
  -H "Content-Type: application/json" \
  -d '{"code": "data = [1, 2, 3, 4, 5]\nprint(f\"Sum: {sum(data)}, Avg: {sum(data)/len(data)}\")"}'

# Custom timeout
curl -X POST http://localhost:8000/tools/python \
  -H "Content-Type: application/json" \
  -d '{"code": "import time\nfor i in range(3):\n    print(i)\n    time.sleep(0.5)", "timeout_s": 5.0}'
```

### Security Notes

⚠️ **Important:** This executor is **NOT** suitable for untrusted multi-tenant environments. It provides basic security through:
- Pattern matching to block dangerous imports
- Subprocess isolation
- Timeout enforcement
- No access to environment variables or secrets

For production use with untrusted code, consider:
- Running in a containerized environment (Docker)
- Using network isolation
- Implementing resource limits (CPU, memory)
- Adding a more sophisticated sandboxing solution

---

## 3. File Ingestion + Document RAG

### Module: `core/docs_ingest.py`

Enables users to upload documents and perform semantic search over them.

**Supported Formats:**
- Plain text (.txt)
- Markdown (.md)
- PDF (.pdf)

**Features:**
- Intelligent text chunking with overlap
- ChromaDB-based vector storage
- Semantic search with sentence transformers
- Per-user document isolation
- File size limits

### API Endpoint: `POST /files/upload`

**Request:**
```bash
curl -X POST http://localhost:8000/files/upload \
  -F "file=@document.pdf" \
  -F "user_id=user123"
```

**Response:**
```json
{
  "ok": true,
  "num_chunks": 15,
  "file_id": "a1b2c3d4e5f6g7h8",
  "filename": "document.pdf",
  "size_mb": 0.85
}
```

### API Endpoint: `POST /files/query`

**Request:**
```json
{
  "q": "machine learning algorithms",
  "user_id": "user123",
  "top_k": 5,
  "file_id": "a1b2c3d4e5f6g7h8"
}
```

**Response:**
```json
{
  "ok": true,
  "matches": [
    {
      "text": "Machine learning algorithms can be categorized into supervised...",
      "file_id": "a1b2c3d4e5f6g7h8",
      "filename": "document.pdf",
      "chunk_index": 3,
      "score": 0.8542
    }
  ],
  "count": 5
}
```

### Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `TOOLS_DOCS_ENABLED` | `true` | Enable/disable document features |
| `MAX_UPLOAD_SIZE_MB` | `10` | Maximum file size for uploads |
| `DOCS_MAX_CHUNKS_PER_FILE` | `500` | Maximum chunks per file |
| `DOCS_CHUNK_SIZE` | `1000` | Chunk size in characters |
| `DOCS_CHUNK_OVERLAP` | `200` | Overlap between chunks |
| `CHROMA_COLLECTION_USER_DOCS` | `user_docs` | ChromaDB collection name |

### Examples

```bash
# Upload a text file
curl -X POST http://localhost:8000/files/upload \
  -F "file=@notes.txt" \
  -F "user_id=alice"

# Upload a PDF
curl -X POST http://localhost:8000/files/upload \
  -F "file=@research_paper.pdf" \
  -F "user_id=alice"

# Search across all user's documents
curl -X POST http://localhost:8000/files/query \
  -H "Content-Type: application/json" \
  -d '{"q": "neural networks", "user_id": "alice", "top_k": 3}'

# Search within a specific file
curl -X POST http://localhost:8000/files/query \
  -H "Content-Type: application/json" \
  -d '{"q": "conclusion", "user_id": "alice", "file_id": "a1b2c3d4e5f6g7h8"}'
```

---

## Integration with Chat Flow

### Math Tool Integration

The math tool can be integrated into the chat flow by:

1. **Auto-detection:** Use `is_calculator_query()` to detect math questions
2. **Explicit commands:** Respond to `/calc` or `/math` commands
3. **LLM prompt enhancement:** Include calculation results in context

Example integration:
```python
from core.calculator import Calculator, is_calculator_query

if is_calculator_query(user_message):
    result = Calculator.evaluate(user_message)
    if result:
        formatted, _ = result
        # Include in LLM context or return directly
        response = f"The result is: {formatted}"
```

### Python Executor Integration

For security, Python execution should be **explicit only**:

1. **Command-based:** Only execute when user sends `/py` or `/python` command
2. **Admin-only:** Restrict to trusted users
3. **Confirmation:** Require explicit confirmation before execution

Example:
```python
if user_message.startswith('/py '):
    code = user_message[4:]
    result = await run_code("python", code)
    response = result['stdout'] if result['success'] else result['error']
```

### Document RAG Integration

Documents can be queried automatically or explicitly:

1. **Auto-query:** Detect document-related questions
2. **Explicit commands:** `/docs` or `/file` commands
3. **Context enhancement:** Include relevant chunks in LLM prompts

Example:
```python
from core.docs_ingest import query_user_docs

# Detect document query
if "/docs" in user_message or "my documents" in user_message.lower():
    matches = query_user_docs(user_id, user_message, top_k=3)
    
    if matches:
        context = "\n\n".join([m['text'] for m in matches])
        # Include in LLM prompt
        prompt = f"Context from user's documents:\n{context}\n\nUser question: {user_message}"
```

---

## Testing

### Run All Tests

```bash
# Simple tests (no network required)
python3 tests/test_tools_simple.py

# Full integration tests (requires network for embeddings)
python3 tests/test_tools_endpoints.py
```

### Test Results

All 18 tests passing:
- ✅ 6 Calculator tests
- ✅ 6 Code execution tests  
- ✅ 6 Document ingestion tests

---

## Dependencies Added

```
PyPDF2>=3.0.0           # PDF text extraction
python-multipart>=0.0.6 # File upload support (FastAPI)
```

Existing dependencies used:
- `chromadb` - Vector database for documents
- `sentence-transformers` - Text embeddings
- `fastapi` - API framework

---

## Security Summary

### Math Tool ✅ Safe
- No arbitrary code execution
- Whitelisted functions only
- Input validation and sanitization

### Python Executor ⚠️ Limited Safety
- **Disabled by default** (`TOOLS_PYTHON_EXEC_ENABLED=false`)
- Basic security through pattern blocking
- Subprocess isolation
- Timeout enforcement
- **NOT suitable for untrusted environments**

### Document RAG ✅ Safe
- File type validation
- Size limits enforced
- No code execution in documents
- User isolation via metadata filtering

---

## Future Enhancements

1. **Math Tool:**
   - Add financial functions (NPV, IRR, etc.)
   - Support for unit conversions
   - Mathematical notation parsing

2. **Python Executor:**
   - Add more language support (JavaScript, Go)
   - Better sandboxing (containers, VMs)
   - Resource usage tracking

3. **Document RAG:**
   - Support for more formats (DOCX, HTML, CSV)
   - OCR for scanned PDFs
   - Document summarization
   - Citation tracking

---

## Files Modified/Created

### Created:
- `core/docs_ingest.py` - Document ingestion module
- `tests/test_tools_simple.py` - Unit tests
- `tests/test_tools_endpoints.py` - Integration tests
- `TOOLS_SUMMARY.md` - This file

### Modified:
- `backend/quantum_api.py` - Added 3 new endpoints
- `requirements.txt` - Added PyPDF2, python-multipart
- `ENV_REFERENCE.md` - Documented new config options

---

## Quick Start

1. **Enable the tools** (add to `.env`):
```bash
TOOLS_MATH_ENABLED=true
TOOLS_PYTHON_EXEC_ENABLED=false  # Keep disabled for security
TOOLS_DOCS_ENABLED=true
```

2. **Start the API:**
```bash
cd backend
uvicorn quantum_api:app --host 0.0.0.0 --port 8000
```

3. **Test the endpoints:**
```bash
# Math
curl -X POST http://localhost:8000/tools/math \
  -H "Content-Type: application/json" \
  -d '{"expr": "sqrt(144)"}'

# Upload a document
curl -X POST http://localhost:8000/files/upload \
  -F "file=@test.txt" \
  -F "user_id=test"

# Query documents
curl -X POST http://localhost:8000/files/query \
  -H "Content-Type: application/json" \
  -d '{"q": "test", "user_id": "test"}'
```

---

**Implementation Complete** ✅
