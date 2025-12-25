# Knowledge Graph Layer - Quick Start Guide

## Overview

The Knowledge Graph layer adds semantic relationship tracking on top of ChromaDB, enabling the AI to understand and leverage connections between concepts extracted from conversations.

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   Conversational AI                      │
├─────────────────────────────────────────────────────────┤
│  User Profile Memory    │    Conversational Memory       │
│  (user_profile_memory)  │   (conversational_memory)      │
├─────────────────────────┴────────────────────────────────┤
│                  Knowledge Graph Layer                   │
│              (concept_extractor + knowledge_graph)       │
├──────────────────────────────────────────────────────────┤
│                      ChromaDB                            │
│              (Vector Storage / Similarity)               │
└──────────────────────────────────────────────────────────┘
```

## Components

### 1. Concept Extractor (`core/concept_extractor.py`)

Extracts concepts from text using NLP:
- **Entities**: People, places, organizations
- **Technologies**: Python, FastAPI, ChromaDB, etc.
- **Relationships**: "X uses Y", "A depends on B"

**Features**:
- spaCy integration for advanced NLP (optional)
- Fallback extraction when spaCy not available
- Noise filtering (stopwords, common terms)

**Example**:
```python
from core.concept_extractor import extract_concepts, extract_relationships

text = "I'm building a Python project using FastAPI and ChromaDB."
concepts = extract_concepts(text)
# Returns: [Concept(text="Python", type="TECH"), ...]

rel_text = "FastAPI depends on Pydantic."
relationships = extract_relationships(rel_text)
# Returns: [{"source": "FastAPI", "target": "Pydantic", "relation": "depends_on"}]
```

### 2. Knowledge Graph (`core/knowledge_graph.py`)

NetworkX-based in-memory graph with persistence:
- **Nodes**: Concepts with metadata (type, timestamps)
- **Edges**: Weighted relationships between concepts
- **Persistence**: GraphML (XML) format to disk

**Features**:
- Add concepts and relationships
- Semantic similarity computation (using embeddings)
- Graph queries (find related concepts, get context)
- ASCII visualization
- Auto-save to disk

**Example**:
```python
from core.knowledge_graph import get_knowledge_graph

kg = get_knowledge_graph()

# Add concepts
kg.add_concept("Python", "TECH")
kg.add_concept("FastAPI", "TECH")

# Add relationships
kg.add_relationship("FastAPI", "Python", "uses", weight=0.95)

# Query
related = kg.find_related("Python", depth=2)
for rel in related:
    print(f"{rel.concept} [{rel.relation_type}] (weight={rel.weight})")

# Visualize
print(kg.visualize_subgraph("Python", depth=1))
```

### 3. Integration Points

#### User Profile Memory
Automatically extracts concepts from user facts and builds knowledge graph.

```python
from core.user_profile_memory import save_user_profile_fact

# Saving a fact automatically updates the knowledge graph
save_user_profile_fact(
    user_id="matteo",
    fact_text="I live in Rome and work with Python"
)
# → Extracts: Rome (PLACE), Python (TECH)
# → Creates relationships
```

#### Conversational Memory
Tracks concepts across conversation turns and enriches context.

```python
from core.conversational_memory import get_conversational_memory

memory = get_conversational_memory()
await memory.add_turn(
    source="telegram",
    source_id="user123",
    user_message="Tell me about Python libraries",
    assistant_response="Python has many libraries like NumPy..."
)
# → Extracts concepts from both messages
# → Updates knowledge graph
# → Future queries can leverage these relationships
```

## Configuration

Add to your `.env` file:

```bash
# Enable/disable knowledge graph
ENABLE_KNOWLEDGE_GRAPH=1

# Semantic similarity threshold for auto-relationships (0.0-1.0)
KG_SIMILARITY_THRESHOLD=0.6

# Graph persistence path
KG_PERSIST_PATH=./data/knowledge_graph.graphml

# Graph size limits
KG_MAX_NODES=10000
KG_MAX_EDGES_PER_NODE=50

# spaCy model (requires: python -m spacy download en_core_web_sm)
SPACY_MODEL=en_core_web_sm

# Concept extraction limits
MIN_CONCEPT_LENGTH=2
MAX_CONCEPT_LENGTH=100
```

## Installation

### Required Dependencies
```bash
pip install networkx python-dotenv
```

### Optional (for enhanced NLP)
```bash
pip install spacy
python -m spacy download en_core_web_sm  # English (small)
# OR
python -m spacy download it_core_news_sm  # Italian
```

**Note**: The system works without spaCy using fallback extraction.

## Usage Examples

### Example 1: Build Knowledge Graph from Conversation

```python
from core.concept_extractor import extract_concepts
from core.knowledge_graph import get_knowledge_graph

kg = get_knowledge_graph()

conversation = """
I'm working on QuantumDev, a Python project.
It uses FastAPI for the API and ChromaDB for vector storage.
The project integrates with NetworkX for knowledge graphs.
"""

# Extract and add concepts
concepts = extract_concepts(conversation)
for concept in concepts:
    kg.add_concept(concept.text, concept.type)

# Infer relationships between concepts
for i, concept in enumerate(concepts[:5]):
    other_concepts = [c.text for j, c in enumerate(concepts) if j != i]
    inferred = kg.infer_relationships(concept.text, other_concepts[:5])
    for target, similarity in inferred:
        if similarity >= 0.6:  # Threshold
            kg.add_relationship(concept.text, target, "related_to", similarity)

# Save graph
kg.save_graph()
```

### Example 2: Query Related Concepts

```python
from core.knowledge_graph import get_knowledge_graph

kg = get_knowledge_graph()

# Find concepts related to "Python" within 2 hops
related = kg.find_related("Python", depth=2, max_results=10)

for rel in related:
    print(f"{rel.concept} - {rel.relation_type} (weight: {rel.weight:.2f}, distance: {rel.distance})")
```

### Example 3: Get Full Context

```python
from core.knowledge_graph import get_knowledge_graph

kg = get_knowledge_graph()

# Get rich context for a concept
context = kg.get_context("Python")
print(context)
```

Output:
```
📊 CONCEPT: Python (TECH)

🔗 RELATIONSHIPS:

  Distance 1:
    - FastAPI [uses] (weight: 0.95)
    - ChromaDB [uses] (weight: 0.90)
    - NumPy [depends_on] (weight: 0.85)
```

### Example 4: Visualize Subgraph

```python
from core.knowledge_graph import get_knowledge_graph

kg = get_knowledge_graph()

# ASCII visualization
viz = kg.visualize_subgraph("Python", depth=2)
print(viz)
```

Output:
```
🔵 Python (center)

  └─ Distance 1:
     ├─ FastAPI [uses] (w=0.95)
     ├─ ChromaDB [uses] (w=0.90)
     └─ NumPy [depends_on] (w=0.85)
```

## Advanced Features

### 1. Semantic Similarity Inference

The knowledge graph can automatically infer relationships based on semantic similarity:

```python
kg = get_knowledge_graph()

# Infer relationships between FastAPI and other Python frameworks
candidates = ["Django", "Flask", "Tornado"]
inferred = kg.infer_relationships("FastAPI", candidates, threshold=0.6)

for target, similarity in inferred:
    kg.add_relationship("FastAPI", target, "similar_to", similarity)
```

### 2. Graph Statistics

```python
stats = kg.get_stats()
print(f"Nodes: {stats['nodes']}")
print(f"Edges: {stats['edges']}")
print(f"Node types: {stats['node_types']}")
print(f"Avg degree: {stats['avg_degree']:.2f}")
```

### 3. Cleanup Old Concepts

```python
# Remove isolated concepts older than 365 days
removed = kg.cleanup_old_concepts(days=365)
print(f"Removed {removed} old concepts")
```

### 4. Graph Persistence

The graph automatically saves to disk, but you can manually control it:

```python
kg = get_knowledge_graph()

# Manual save
kg.save_graph()

# Load existing graph (happens automatically on init)
# kg._load_graph()  # Called in __init__
```

## Testing

Run the test suite:

```bash
cd "Contabo VPS/quantumdev-open"
python tests/test_knowledge_graph.py
```

Test coverage includes:
- Concept extraction (with and without spaCy)
- Graph construction and queries
- Relationship inference
- Persistence and loading
- Integration with memory systems

## Performance Considerations

### Memory Usage
- **In-memory graph**: NetworkX stores the full graph in RAM
- **Typical size**: 10K nodes ~ 1-2 MB RAM
- **Limit**: Configure `KG_MAX_NODES` (default: 10,000)

### Disk Usage
- **GraphML file**: XML format, human-readable
- **Typical size**: 10K nodes ~ 2-5 MB disk
- **Location**: Configurable via `KG_PERSIST_PATH`

### Performance
- **Add concept**: O(1)
- **Add relationship**: O(1)
- **Find related (BFS)**: O(E + V) where E=edges, V=vertices
- **Semantic similarity**: O(n) for n candidates

## Troubleshooting

### "spaCy not installed"
- **Solution**: Install spaCy or use fallback extraction
- **Fallback**: System automatically uses pattern-based extraction

### "Knowledge graph not available"
- **Check**: `ENABLE_KNOWLEDGE_GRAPH=1` in `.env`
- **Check**: NetworkX installed (`pip install networkx`)

### "Failed to load embedding model"
- **Check**: sentence-transformers installed
- **Note**: Required for semantic similarity computation
- **Fallback**: Relationships can still be added manually

### Graph file grows too large
- **Solution**: Run periodic cleanup
- **Solution**: Reduce `KG_MAX_NODES` limit
- **Solution**: Delete old graph file and restart

## Answers to Problem Statement Questions

### 1. NetworkX sufficient or need graph database?
**Answer**: NetworkX is sufficient for the use case:
- ✅ Lightweight (no external database)
- ✅ In-memory for fast queries
- ✅ GraphML persistence for durability
- ✅ No licensing costs
- ✅ Easy to integrate

For future scaling (>100K nodes), consider Neo4j or TigerGraph.

### 2. Which spaCy model?
**Answer**: `en_core_web_sm` (default) with fallback:
- ✅ Small and fast (14 MB)
- ✅ Good accuracy for entity recognition
- ✅ Fallback extraction when not available
- 🔄 Can upgrade to `en_core_web_lg` for better accuracy

### 3. Italian spaCy model?
**Answer**: Configurable via `SPACY_MODEL=it_core_news_sm`:
- ✅ Italian model supported (`it_core_news_sm`)
- ✅ Fallback works for Italian too
- ✅ Tech terms recognized regardless of language

### 4. Graph persistence?
**Answer**: GraphML (XML) format:
- ✅ Cross-platform compatible
- ✅ Human-readable for debugging
- ✅ Standard format supported by many tools
- ✅ Easy to import/export

### 5. Graph visualization?
**Answer**: ASCII visualization built-in:
- ✅ `visualize_subgraph()` for terminal output
- ✅ Can integrate pyvis/graphviz for web visualization (future)
- ✅ GraphML compatible with Gephi, Cytoscape

## Future Enhancements

Potential improvements:
1. **Web Visualization**: Integration with pyvis for interactive graphs
2. **Query Language**: Graph query DSL (similar to Cypher)
3. **Temporal Tracking**: Track concept evolution over time
4. **Community Detection**: Find concept clusters
5. **Graph Analytics**: PageRank, centrality measures
6. **Incremental Learning**: Update relationships based on feedback

## Support

For issues or questions:
1. Check logs: `log.debug()` statements throughout
2. Run tests: `python tests/test_knowledge_graph.py`
3. Check configuration: Environment variables
4. Review this guide: Common patterns and examples

---

**Version**: 1.0.0  
**Author**: QuantumDev Team  
**Last Updated**: 2025-12-18
