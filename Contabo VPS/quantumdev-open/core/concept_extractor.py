#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/concept_extractor.py — Concept Extraction for Knowledge Graph

Extracts concepts from text using spaCy NLP:
- People, places, organizations, technologies
- Projects, ideas, and important terms
- Filters noise (stopwords, common terms)

Author: QuantumDev
"""

import os
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# Environment configuration
SPACY_MODEL = os.getenv("SPACY_MODEL", "en_core_web_sm")
MIN_CONCEPT_LENGTH = int(os.getenv("MIN_CONCEPT_LENGTH", "2"))
MAX_CONCEPT_LENGTH = int(os.getenv("MAX_CONCEPT_LENGTH", "100"))

# Lazy load spaCy model
_nlp = None
_nlp_model_name = None


def _get_nlp():
    """Lazy load spaCy NLP model."""
    global _nlp, _nlp_model_name
    
    if _nlp is None or _nlp_model_name != SPACY_MODEL:
        try:
            import spacy
            _nlp = spacy.load(SPACY_MODEL)
            _nlp_model_name = SPACY_MODEL
            log.info(f"Loaded spaCy model: {SPACY_MODEL}")
        except OSError:
            log.warning(f"spaCy model {SPACY_MODEL} not found, using blank model")
            import spacy
            # Create blank model if specific model not available
            lang = SPACY_MODEL.split("_")[0] if "_" in SPACY_MODEL else "en"
            _nlp = spacy.blank(lang)
            _nlp_model_name = f"blank_{lang}"
    
    return _nlp


# Common stopwords and noise terms (language-agnostic)
NOISE_TERMS = {
    # English
    "thing", "stuff", "something", "someone", "anyone", "everyone",
    "somewhere", "anywhere", "everywhere", "nothing", "nobody",
    # Italian
    "cosa", "roba", "qualcosa", "qualcuno", "niente", "nessuno",
    # Common
    "etc", "ex", "via", "vs", "aka", "i.e", "e.g",
}

# Technology and programming related terms (always include)
TECH_TERMS = {
    "python", "javascript", "java", "go", "rust", "c++", "typescript",
    "react", "vue", "angular", "django", "flask", "fastapi", "nodejs",
    "api", "rest", "graphql", "sql", "nosql", "database", "redis",
    "docker", "kubernetes", "aws", "azure", "gcp", "cloud",
    "ai", "ml", "nlp", "llm", "neural", "model", "embedding",
    "chromadb", "vector", "gpu", "cpu", "memory", "cache",
}


@dataclass
class Concept:
    """Extracted concept with metadata."""
    text: str
    type: str  # PERSON, ORG, GPE, TECH, PRODUCT, etc.
    context: str = ""
    confidence: float = 1.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "text": self.text,
            "type": self.type,
            "context": self.context,
            "confidence": self.confidence,
        }
    
    def __hash__(self):
        """Make hashable for set operations."""
        return hash((self.text.lower(), self.type))
    
    def __eq__(self, other):
        """Equality based on text and type."""
        if not isinstance(other, Concept):
            return False
        return self.text.lower() == other.text.lower() and self.type == other.type


def _is_valid_concept(text: str) -> bool:
    """Check if text is a valid concept."""
    if not text or not text.strip():
        return False
    
    text = text.strip()
    
    # Length check
    if len(text) < MIN_CONCEPT_LENGTH or len(text) > MAX_CONCEPT_LENGTH:
        return False
    
    # Must contain at least one letter
    if not any(c.isalpha() for c in text):
        return False
    
    # Check if noise term
    if text.lower() in NOISE_TERMS:
        return False
    
    return True


def _normalize_concept(text: str) -> str:
    """Normalize concept text."""
    # Remove extra whitespace
    text = " ".join(text.split())
    
    # Capitalize properly for entities
    if text.isupper() or text.islower():
        text = text.title()
    
    return text.strip()


def extract_concepts(text: str, context: str = "") -> List[Concept]:
    """
    Extract concepts from text using spaCy NLP.
    
    Args:
        text: Input text to analyze
        context: Optional context for the concepts
        
    Returns:
        List of extracted Concept objects
    """
    if not text or not text.strip():
        return []
    
    nlp = _get_nlp()
    if nlp is None:
        log.warning("spaCy NLP not available")
        return []
    
    concepts: Set[Concept] = set()
    
    try:
        doc = nlp(text)
        
        # Extract named entities
        for ent in doc.ents:
            if not _is_valid_concept(ent.text):
                continue
            
            normalized = _normalize_concept(ent.text)
            
            # Map spaCy entity types to our types
            concept_type = ent.label_
            if concept_type in ("PERSON", "PER"):
                concept_type = "PERSON"
            elif concept_type in ("ORG", "ORGANIZATION"):
                concept_type = "ORG"
            elif concept_type in ("GPE", "LOC", "LOCATION"):
                concept_type = "PLACE"
            elif concept_type in ("PRODUCT", "WORK_OF_ART"):
                concept_type = "PRODUCT"
            elif concept_type in ("EVENT",):
                concept_type = "EVENT"
            else:
                concept_type = "ENTITY"
            
            concepts.add(Concept(
                text=normalized,
                type=concept_type,
                context=context,
                confidence=0.9
            ))
        
        # Extract technology terms (noun chunks and keywords)
        for chunk in doc.noun_chunks:
            chunk_text = chunk.text.strip()
            chunk_lower = chunk_text.lower()
            
            # Check if it's a tech term
            if chunk_lower in TECH_TERMS:
                normalized = _normalize_concept(chunk_text)
                concepts.add(Concept(
                    text=normalized,
                    type="TECH",
                    context=context,
                    confidence=0.95
                ))
            # Check for compound tech terms (e.g., "REST API", "machine learning")
            elif any(tech in chunk_lower for tech in TECH_TERMS):
                if _is_valid_concept(chunk_text):
                    normalized = _normalize_concept(chunk_text)
                    concepts.add(Concept(
                        text=normalized,
                        type="TECH",
                        context=context,
                        confidence=0.85
                    ))
        
        # Extract important nouns (potential projects/ideas)
        for token in doc:
            if token.pos_ in ("NOUN", "PROPN") and not token.is_stop:
                if _is_valid_concept(token.text):
                    token_lower = token.text.lower()
                    
                    # Skip if already captured as entity or tech
                    if any(c.text.lower() == token_lower for c in concepts):
                        continue
                    
                    # Check if it's a tech term
                    if token_lower in TECH_TERMS:
                        normalized = _normalize_concept(token.text)
                        concepts.add(Concept(
                            text=normalized,
                            type="TECH",
                            context=context,
                            confidence=0.8
                        ))
                    # Important noun (potential project/idea)
                    elif len(token.text) >= 3 and token.text[0].isupper():
                        normalized = _normalize_concept(token.text)
                        concepts.add(Concept(
                            text=normalized,
                            type="CONCEPT",
                            context=context,
                            confidence=0.7
                        ))
        
    except Exception as e:
        log.error(f"Concept extraction failed: {e}")
    
    # Convert set to list and sort by confidence
    result = sorted(list(concepts), key=lambda c: c.confidence, reverse=True)
    
    log.debug(f"Extracted {len(result)} concepts from text ({len(text)} chars)")
    return result


def extract_relationships(text: str) -> List[Dict[str, str]]:
    """
    Extract explicit relationships from text.
    
    Looks for patterns like:
    - "X is related to Y"
    - "X depends on Y"
    - "X uses Y"
    - "X parte di Y" (Italian)
    
    Args:
        text: Input text
        
    Returns:
        List of relationship dicts with source, target, and relation type
    """
    import re
    
    relationships = []
    
    # English patterns
    patterns_en = [
        (r"(\w+)\s+is\s+related\s+to\s+(\w+)", "related_to"),
        (r"(\w+)\s+depends\s+on\s+(\w+)", "depends_on"),
        (r"(\w+)\s+uses\s+(\w+)", "uses"),
        (r"(\w+)\s+requires\s+(\w+)", "requires"),
        (r"(\w+)\s+is\s+part\s+of\s+(\w+)", "part_of"),
    ]
    
    # Italian patterns
    patterns_it = [
        (r"(\w+)\s+è\s+relat[oa]\s+a\s+(\w+)", "related_to"),
        (r"(\w+)\s+dipende\s+da\s+(\w+)", "depends_on"),
        (r"(\w+)\s+usa\s+(\w+)", "uses"),
        (r"(\w+)\s+richiede\s+(\w+)", "requires"),
        (r"(\w+)\s+è\s+parte\s+di\s+(\w+)", "part_of"),
        (r"(\w+)\s+fa\s+parte\s+di\s+(\w+)", "part_of"),
    ]
    
    all_patterns = patterns_en + patterns_it
    
    for pattern, relation_type in all_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            source = _normalize_concept(match.group(1))
            target = _normalize_concept(match.group(2))
            
            if _is_valid_concept(source) and _is_valid_concept(target):
                relationships.append({
                    "source": source,
                    "target": target,
                    "relation": relation_type,
                })
    
    return relationships


def download_spacy_model(model_name: str = SPACY_MODEL) -> bool:
    """
    Download spaCy model if not already installed.
    
    Args:
        model_name: spaCy model name (e.g., 'en_core_web_sm')
        
    Returns:
        True if successful, False otherwise
    """
    try:
        import spacy
        
        # Try to load it first
        try:
            spacy.load(model_name)
            log.info(f"spaCy model {model_name} already installed")
            return True
        except OSError:
            pass
        
        # Download it
        log.info(f"Downloading spaCy model: {model_name}")
        import subprocess
        result = subprocess.run(
            ["python", "-m", "spacy", "download", model_name],
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            log.info(f"Successfully downloaded {model_name}")
            return True
        else:
            log.error(f"Failed to download {model_name}: {result.stderr}")
            return False
            
    except Exception as e:
        log.error(f"Error downloading spaCy model: {e}")
        return False


# === Test ===
if __name__ == "__main__":
    # Test concept extraction
    print("🧪 Testing Concept Extractor")
    print("=" * 60)
    
    test_text = """
    I'm working on a Python project using FastAPI and ChromaDB.
    The project is called QuantumDev and it uses machine learning
    for knowledge graph construction. I live in Rome and collaborate
    with developers in Milan. We're integrating spaCy for NLP tasks.
    """
    
    concepts = extract_concepts(test_text)
    print(f"\n📊 Extracted {len(concepts)} concepts:")
    for concept in concepts:
        print(f"  - {concept.text} ({concept.type}) [confidence: {concept.confidence}]")
    
    # Test relationship extraction
    rel_text = "Python uses spaCy. FastAPI depends on Pydantic. ChromaDB is related to vector search."
    relationships = extract_relationships(rel_text)
    print(f"\n🔗 Extracted {len(relationships)} relationships:")
    for rel in relationships:
        print(f"  - {rel['source']} --[{rel['relation']}]--> {rel['target']}")
    
    print("\n✅ Test complete!")
