#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/artifacts.py — Artifacts System for QuantumDev Max

Features:
- Structured content persistence (code, HTML, JSON, tables)
- Redis storage with 7-day TTL
- Syntax highlighting support
- Version tracking
- Content type detection

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import logging
import re
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

import redis
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        m = re.search(r"-?\d+", raw)
        return int(m.group(0)) if m else default
    except Exception:
        return default


ENABLE_ARTIFACTS = _env_bool("ENABLE_ARTIFACTS", True)
ARTIFACT_TTL = _env_int("ARTIFACT_TTL", 604800)  # 7 days
MAX_ARTIFACTS_PER_USER = _env_int("MAX_ARTIFACTS_PER_USER", 100)  # Max artifacts per user

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = _env_int("REDIS_PORT", 6379)
REDIS_DB = _env_int("REDIS_DB", 0)

# Redis client
_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )
    return _redis_client


# === Enums ===
class ArtifactType(str, Enum):
    """Types of artifacts."""
    CODE = "code"
    HTML = "html"
    MARKDOWN = "markdown"
    JSON = "json"
    TABLE = "table"
    TEXT = "text"
    SVG = "svg"
    MERMAID = "mermaid"


class Language(str, Enum):
    """Programming languages for code artifacts."""
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    TYPESCRIPT = "typescript"
    JAVA = "java"
    CPP = "cpp"
    C = "c"
    CSHARP = "csharp"
    GO = "go"
    RUST = "rust"
    SQL = "sql"
    BASH = "bash"
    YAML = "yaml"
    JSON = "json"
    HTML = "html"
    CSS = "css"
    UNKNOWN = "unknown"


# === Data Classes ===
@dataclass
class Artifact:
    """Structured content artifact."""
    id: str
    type: ArtifactType
    title: str
    content: str
    language: Optional[Language] = None
    version: int = 1
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = ""  # "tg", "web", "api"
    source_id: str = ""  # user/chat identifier
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "content": self.content,
            "language": self.language.value if self.language else None,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
            "source": self.source,
            "source_id": self.source_id,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Artifact":
        artifact_type = data.get("type", "text")
        language = data.get("language")
        
        return cls(
            id=data.get("id", ""),
            type=ArtifactType(artifact_type) if artifact_type else ArtifactType.TEXT,
            title=data.get("title", ""),
            content=data.get("content", ""),
            language=Language(language) if language else None,
            version=data.get("version", 1),
            created_at=data.get("created_at", int(time.time())),
            updated_at=data.get("updated_at", int(time.time())),
            metadata=data.get("metadata", {}),
            source=data.get("source", ""),
            source_id=data.get("source_id", ""),
        )
    
    @property
    def size_bytes(self) -> int:
        """Get content size in bytes."""
        return len(self.content.encode('utf-8'))
    
    @property
    def line_count(self) -> int:
        """Get line count."""
        return len(self.content.split('\n'))
    
    def format_display(self, max_lines: int = 50) -> str:
        """Format artifact for display."""
        lines = [
            f"📦 **{self.title}** (v{self.version})",
            f"Type: {self.type.value}",
        ]
        
        if self.language:
            lines.append(f"Language: {self.language.value}")
        
        lines.append(f"Size: {self.size_bytes} bytes, {self.line_count} lines")
        lines.append("")
        
        # Content preview
        content_lines = self.content.split('\n')
        if len(content_lines) > max_lines:
            preview = '\n'.join(content_lines[:max_lines])
            lines.append(f"```{self.language.value if self.language else ''}")
            lines.append(preview)
            lines.append("...")
            lines.append(f"(+{len(content_lines) - max_lines} more lines)")
            lines.append("```")
        else:
            lines.append(f"```{self.language.value if self.language else ''}")
            lines.append(self.content)
            lines.append("```")
        
        return '\n'.join(lines)
    
    def format_code_block(self) -> str:
        """Format as markdown code block."""
        lang = self.language.value if self.language else ""
        return f"```{lang}\n{self.content}\n```"


@dataclass
class TableArtifact(Artifact):
    """Table-specific artifact with structured data."""
    headers: List[str] = field(default_factory=list)
    rows: List[List[Any]] = field(default_factory=list)
    
    def __post_init__(self):
        self.type = ArtifactType.TABLE
        if self.headers and self.rows and not self.content:
            self._generate_content()
    
    def _generate_content(self) -> None:
        """Generate markdown table content."""
        if not self.headers or not self.rows:
            return
        
        lines = []
        # Header
        lines.append("| " + " | ".join(str(h) for h in self.headers) + " |")
        # Separator
        lines.append("| " + " | ".join("---" for _ in self.headers) + " |")
        # Rows
        for row in self.rows:
            lines.append("| " + " | ".join(str(c) for c in row) + " |")
        
        self.content = '\n'.join(lines)
    
    def to_dict(self) -> Dict[str, Any]:
        base = super().to_dict()
        base["headers"] = self.headers
        base["rows"] = self.rows
        return base


# === Language Detection ===
def detect_language(code: str, hint: Optional[str] = None) -> Language:
    """
    Detect programming language from code.
    
    Args:
        code: Code content
        hint: Optional filename or extension hint
        
    Returns:
        Detected Language
    """
    if hint:
        hint_lower = hint.lower()
        ext_map = {
            '.py': Language.PYTHON,
            '.js': Language.JAVASCRIPT,
            '.ts': Language.TYPESCRIPT,
            '.java': Language.JAVA,
            '.cpp': Language.CPP,
            '.c': Language.C,
            '.cs': Language.CSHARP,
            '.go': Language.GO,
            '.rs': Language.RUST,
            '.sql': Language.SQL,
            '.sh': Language.BASH,
            '.bash': Language.BASH,
            '.yml': Language.YAML,
            '.yaml': Language.YAML,
            '.json': Language.JSON,
            '.html': Language.HTML,
            '.css': Language.CSS,
        }
        for ext, lang in ext_map.items():
            if hint_lower.endswith(ext):
                return lang
    
    # Pattern-based detection
    patterns = [
        (r'^\s*def\s+\w+\s*\(|^\s*class\s+\w+|^\s*import\s+\w+|^\s*from\s+\w+\s+import', Language.PYTHON),
        (r'^\s*function\s+\w+|^\s*const\s+\w+\s*=|^\s*let\s+\w+\s*=|^\s*var\s+\w+\s*=', Language.JAVASCRIPT),
        (r'^\s*interface\s+\w+|:\s*(string|number|boolean|any)\s*[;,)]', Language.TYPESCRIPT),
        (r'^\s*public\s+class\s+\w+|^\s*package\s+\w+', Language.JAVA),
        (r'^\s*#include\s*<|^\s*using\s+namespace', Language.CPP),
        (r'^\s*func\s+\w+|^\s*package\s+main', Language.GO),
        (r'^\s*fn\s+\w+|^\s*let\s+mut\s+|^\s*impl\s+', Language.RUST),
        (r'^\s*SELECT\s+|^\s*INSERT\s+|^\s*UPDATE\s+|^\s*CREATE\s+TABLE', Language.SQL),
        (r'^#!/bin/(ba)?sh|^\s*echo\s+', Language.BASH),
        (r'^\s*<html|^\s*<!DOCTYPE', Language.HTML),
        (r'^\s*\{|\[\s*\{', Language.JSON),
        (r'^\s*[a-z_-]+:\s*[|\-]?', Language.YAML),
    ]
    
    for pattern, lang in patterns:
        if re.search(pattern, code, re.MULTILINE | re.IGNORECASE):
            return lang
    
    return Language.UNKNOWN


# === Artifacts Manager ===
class ArtifactsManager:
    """
    Manages structured artifacts with persistence.
    """
    
    def __init__(self):
        """Initialize Artifacts Manager."""
        self._cache: Dict[str, Artifact] = {}
        log.info(f"ArtifactsManager initialized: ttl={ARTIFACT_TTL}s")
    
    def _generate_id(self, content: str, type: ArtifactType) -> str:
        """Generate unique artifact ID."""
        ts = int(time.time())
        h = hashlib.sha256(f"{type.value}:{content[:100]}:{ts}".encode()).hexdigest()[:12]
        return f"art_{h}"
    
    def _redis_key(self, artifact_id: str) -> str:
        """Generate Redis key for artifact."""
        return f"artifact:{artifact_id}"
    
    def _user_index_key(self, source: str, source_id: str) -> str:
        """Generate Redis key for user's artifact index."""
        return f"artifacts_idx:{source}:{source_id}"
    
    async def create(
        self,
        type: ArtifactType,
        title: str,
        content: str,
        language: Optional[Language] = None,
        source: str = "",
        source_id: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Artifact:
        """
        Create a new artifact.
        
        Args:
            type: Artifact type
            title: Artifact title
            content: Artifact content
            language: Programming language (for code)
            source: Source identifier
            source_id: User/chat identifier
            metadata: Optional metadata
            
        Returns:
            Created Artifact
        """
        artifact_id = self._generate_id(content, type)
        
        # Auto-detect language for code
        if type == ArtifactType.CODE and not language:
            language = detect_language(content)
        
        artifact = Artifact(
            id=artifact_id,
            type=type,
            title=title,
            content=content,
            language=language,
            source=source,
            source_id=source_id,
            metadata=metadata or {},
        )
        
        # Save to Redis
        await self._save(artifact)
        
        # Add to user index
        if source and source_id:
            await self._add_to_index(source, source_id, artifact_id)
        
        log.info(f"Artifact created: {artifact_id} ({type.value})")
        return artifact
    
    async def create_code(
        self,
        title: str,
        code: str,
        language: Optional[Union[Language, str]] = None,
        source: str = "",
        source_id: str = "",
    ) -> Artifact:
        """Create a code artifact."""
        lang = None
        if language:
            if isinstance(language, str):
                try:
                    lang = Language(language.lower())
                except ValueError:
                    lang = detect_language(code, language)
            else:
                lang = language
        
        return await self.create(
            type=ArtifactType.CODE,
            title=title,
            content=code,
            language=lang,
            source=source,
            source_id=source_id,
        )
    
    async def create_table(
        self,
        title: str,
        headers: List[str],
        rows: List[List[Any]],
        source: str = "",
        source_id: str = "",
    ) -> TableArtifact:
        """Create a table artifact."""
        artifact_id = self._generate_id(str(headers) + str(rows), ArtifactType.TABLE)
        
        artifact = TableArtifact(
            id=artifact_id,
            type=ArtifactType.TABLE,
            title=title,
            content="",
            headers=headers,
            rows=rows,
            source=source,
            source_id=source_id,
        )
        
        await self._save(artifact)
        
        if source and source_id:
            await self._add_to_index(source, source_id, artifact_id)
        
        log.info(f"Table artifact created: {artifact_id}")
        return artifact
    
    async def create_json(
        self,
        title: str,
        data: Union[Dict, List],
        source: str = "",
        source_id: str = "",
    ) -> Artifact:
        """Create a JSON artifact."""
        content = json.dumps(data, indent=2, ensure_ascii=False)
        return await self.create(
            type=ArtifactType.JSON,
            title=title,
            content=content,
            language=Language.JSON,
            source=source,
            source_id=source_id,
        )
    
    async def create_html(
        self,
        title: str,
        html: str,
        source: str = "",
        source_id: str = "",
    ) -> Artifact:
        """Create an HTML artifact."""
        return await self.create(
            type=ArtifactType.HTML,
            title=title,
            content=html,
            language=Language.HTML,
            source=source,
            source_id=source_id,
        )
    
    async def _save(self, artifact: Artifact) -> bool:
        """Save artifact to Redis."""
        try:
            redis_client = _get_redis()
            redis_client.setex(
                self._redis_key(artifact.id),
                ARTIFACT_TTL,
                json.dumps(artifact.to_dict()),
            )
            self._cache[artifact.id] = artifact
            return True
        except Exception as e:
            log.error(f"Redis save artifact error: {e}")
            return False
    
    async def _add_to_index(self, source: str, source_id: str, artifact_id: str) -> None:
        """Add artifact to user's index."""
        try:
            redis_client = _get_redis()
            key = self._user_index_key(source, source_id)
            redis_client.lpush(key, artifact_id)
            redis_client.ltrim(key, 0, MAX_ARTIFACTS_PER_USER - 1)  # Keep max configured
            redis_client.expire(key, ARTIFACT_TTL)
        except Exception as e:
            log.warning(f"Redis add to index error: {e}")
    
    async def get(self, artifact_id: str) -> Optional[Artifact]:
        """
        Get artifact by ID.
        
        Args:
            artifact_id: Artifact ID
            
        Returns:
            Artifact if found
        """
        # Check cache
        if artifact_id in self._cache:
            return self._cache[artifact_id]
        
        # Check Redis
        try:
            redis_client = _get_redis()
            data = redis_client.get(self._redis_key(artifact_id))
            if data:
                artifact = Artifact.from_dict(json.loads(data))
                self._cache[artifact_id] = artifact
                return artifact
        except Exception as e:
            log.warning(f"Redis get artifact error: {e}")
        
        return None
    
    async def update(
        self,
        artifact_id: str,
        content: Optional[str] = None,
        title: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Artifact]:
        """
        Update an existing artifact.
        
        Args:
            artifact_id: Artifact ID
            content: New content
            title: New title
            metadata: Updated metadata
            
        Returns:
            Updated Artifact if found
        """
        artifact = await self.get(artifact_id)
        if not artifact:
            return None
        
        if content is not None:
            artifact.content = content
        if title is not None:
            artifact.title = title
        if metadata is not None:
            artifact.metadata.update(metadata)
        
        artifact.version += 1
        artifact.updated_at = int(time.time())
        
        await self._save(artifact)
        log.info(f"Artifact updated: {artifact_id} (v{artifact.version})")
        return artifact
    
    async def delete(self, artifact_id: str) -> bool:
        """
        Delete an artifact.
        
        Args:
            artifact_id: Artifact ID
            
        Returns:
            True if deleted
        """
        # Remove from cache
        if artifact_id in self._cache:
            del self._cache[artifact_id]
        
        # Remove from Redis
        try:
            redis_client = _get_redis()
            redis_client.delete(self._redis_key(artifact_id))
            log.info(f"Artifact deleted: {artifact_id}")
            return True
        except Exception as e:
            log.error(f"Redis delete artifact error: {e}")
            return False
    
    async def list_user_artifacts(
        self,
        source: str,
        source_id: str,
        limit: int = 20,
    ) -> List[Artifact]:
        """
        List user's artifacts.
        
        Args:
            source: Source identifier
            source_id: User/chat identifier
            limit: Maximum number of artifacts
            
        Returns:
            List of Artifacts
        """
        try:
            redis_client = _get_redis()
            key = self._user_index_key(source, source_id)
            artifact_ids = redis_client.lrange(key, 0, limit - 1)
            
            artifacts = []
            for aid in artifact_ids:
                artifact = await self.get(aid)
                if artifact:
                    artifacts.append(artifact)
            
            return artifacts
        except Exception as e:
            log.warning(f"List user artifacts error: {e}")
            return []
    
    async def search_artifacts(
        self,
        query: str,
        source: Optional[str] = None,
        source_id: Optional[str] = None,
        type_filter: Optional[ArtifactType] = None,
        limit: int = 10,
    ) -> List[Artifact]:
        """
        Search artifacts by content.
        
        Args:
            query: Search query
            source: Filter by source
            source_id: Filter by source_id
            type_filter: Filter by type
            limit: Maximum results
            
        Returns:
            List of matching Artifacts
        """
        if source and source_id:
            artifacts = await self.list_user_artifacts(source, source_id, 100)
        else:
            artifacts = list(self._cache.values())
        
        query_lower = query.lower()
        matches = []
        
        for artifact in artifacts:
            if type_filter and artifact.type != type_filter:
                continue
            
            # Simple text search
            if (query_lower in artifact.title.lower() or 
                query_lower in artifact.content.lower()):
                matches.append(artifact)
        
        return matches[:limit]


# === Singleton Instance ===
_manager_instance: Optional[ArtifactsManager] = None


def get_artifacts_manager() -> ArtifactsManager:
    """
    Get or create ArtifactsManager singleton.
    
    Returns:
        ArtifactsManager instance
    """
    global _manager_instance
    
    if not ENABLE_ARTIFACTS:
        log.warning("Artifacts are disabled")
    
    if _manager_instance is None:
        _manager_instance = ArtifactsManager()
    
    return _manager_instance


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🧪 Testing Artifacts System")
        print("=" * 60)
        
        manager = get_artifacts_manager()
        
        # Test code artifact
        code_artifact = await manager.create_code(
            title="Hello World Python",
            code='''def hello():
    print("Hello, World!")

if __name__ == "__main__":
    hello()
''',
            language="python",
            source="test",
            source_id="user123",
        )
        print(f"Code artifact: {code_artifact.id}")
        print(f"Language detected: {code_artifact.language}")
        
        # Test table artifact
        table_artifact = await manager.create_table(
            title="Performance Comparison",
            headers=["Model", "Speed", "Accuracy"],
            rows=[
                ["Qwen 32B", "0.8s", "95%"],
                ["GPT-4", "1.2s", "97%"],
                ["Claude", "0.9s", "96%"],
            ],
            source="test",
            source_id="user123",
        )
        print(f"\nTable artifact: {table_artifact.id}")
        print(table_artifact.content)
        
        # Test JSON artifact
        json_artifact = await manager.create_json(
            title="API Response",
            data={"status": "ok", "data": [1, 2, 3]},
            source="test",
            source_id="user123",
        )
        print(f"\nJSON artifact: {json_artifact.id}")
        
        # Test retrieval
        retrieved = await manager.get(code_artifact.id)
        print(f"\nRetrieved: {retrieved.title if retrieved else 'Not found'}")
        
        # Test listing
        user_artifacts = await manager.list_user_artifacts("test", "user123")
        print(f"\nUser has {len(user_artifacts)} artifacts")
        
        # Test display
        print("\n" + code_artifact.format_display(max_lines=10))
        
        # Cleanup
        await manager.delete(code_artifact.id)
        await manager.delete(table_artifact.id)
        await manager.delete(json_artifact.id)
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
