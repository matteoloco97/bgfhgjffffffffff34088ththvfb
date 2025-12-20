#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/knowledge_graph.py — Knowledge Graph Layer on ChromaDB

Lightweight in-memory knowledge graph using NetworkX:
- Nodes: concepts extracted from conversations
- Edges: semantic relationships with weights
- Persistence: GraphML (XML format) to disk
- Integration: Complements ChromaDB for relationship tracking

Author: QuantumDev
"""

import os
import time
import logging
from typing import List, Dict, Any, Optional, Set, Tuple
from dataclasses import dataclass, asdict
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# Lazy import numpy for semantic similarity
_np = None

def _get_numpy():
    """Lazy import numpy."""
    global _np
    if _np is None:
        try:
            import numpy as np
            _np = np
        except ImportError:
            log.warning("NumPy not installed, semantic similarity will be limited")
            _np = False
    return _np if _np is not False else None

# Environment configuration
ENABLE_KNOWLEDGE_GRAPH = os.getenv("ENABLE_KNOWLEDGE_GRAPH", "1").strip() in ("1", "true", "yes", "on")
KG_SIMILARITY_THRESHOLD = float(os.getenv("KG_SIMILARITY_THRESHOLD", "0.6"))
KG_PERSIST_PATH = os.getenv("KG_PERSIST_PATH", "./data/knowledge_graph.graphml")
KG_MAX_NODES = int(os.getenv("KG_MAX_NODES", "10000"))
KG_MAX_EDGES_PER_NODE = int(os.getenv("KG_MAX_EDGES_PER_NODE", "50"))

# Lazy imports
_nx = None
_embedding_function = None


def _get_networkx():
    """Lazy import NetworkX."""
    global _nx
    if _nx is None:
        try:
            import networkx as nx
            _nx = nx
            log.info("NetworkX loaded successfully")
        except ImportError:
            log.warning("NetworkX not installed. Install with: pip install networkx")
            _nx = False
    return _nx if _nx is not False else None


def _get_embedding_function():
    """Get embedding function from sentence-transformers."""
    global _embedding_function
    if _embedding_function is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
            # Use the full model name as-is for SentenceTransformer
            # SentenceTransformer handles both formats: "org/model" and "model"
            _embedding_function = SentenceTransformer(model_name)
            log.info(f"Loaded embedding model: {model_name}")
        except Exception as e:
            log.warning(f"Failed to load embedding model: {e}")
            _embedding_function = False
    return _embedding_function if _embedding_function is not False else None


@dataclass
class RelatedConcept:
    """Related concept with relationship metadata."""
    concept: str
    relation_type: str
    weight: float
    distance: int  # graph distance from source
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


class KnowledgeGraph:
    """
    Knowledge Graph Manager using NetworkX.
    
    Features:
    - Add concepts as nodes
    - Create relationships as weighted edges
    - Compute semantic similarity between concepts
    - Query related concepts with depth
    - Persist graph to disk (GraphML format)
    - ASCII visualization of subgraphs
    """
    
    def __init__(self):
        """Initialize Knowledge Graph."""
        nx = _get_networkx()
        if nx is None:
            raise ImportError("NetworkX is required. Install with: pip install networkx")
        
        self.graph = nx.DiGraph()
        self._last_modified = time.time()
        self._auto_save = True
        
        # Load existing graph if available
        self._load_graph()
        
        log.info(
            f"KnowledgeGraph initialized: {self.graph.number_of_nodes()} nodes, "
            f"{self.graph.number_of_edges()} edges"
        )
    
    def _load_graph(self) -> bool:
        """Load graph from disk if exists."""
        nx = _get_networkx()
        if not os.path.exists(KG_PERSIST_PATH):
            return False
        
        try:
            import json
            loaded_graph = nx.read_graphml(KG_PERSIST_PATH)
            
            # Convert to DiGraph if needed
            if not isinstance(loaded_graph, nx.DiGraph):
                self.graph = nx.DiGraph(loaded_graph)
            else:
                self.graph = loaded_graph
            
            # Deserialize JSON strings back to lists/dicts
            for node, data in self.graph.nodes(data=True):
                for key, value in list(data.items()):
                    if isinstance(value, str):
                        try:
                            # Try to parse as JSON
                            parsed = json.loads(value)
                            if isinstance(parsed, (list, dict)):
                                data[key] = parsed
                        except (json.JSONDecodeError, ValueError):
                            # Not JSON, keep as string
                            pass
            
            log.info(f"Loaded knowledge graph from {KG_PERSIST_PATH}")
            return True
        except Exception as e:
            log.error(f"Failed to load knowledge graph: {e}")
            return False
    
    def save_graph(self) -> bool:
        """Save graph to disk (GraphML format)."""
        nx = _get_networkx()
        if self.graph.number_of_nodes() == 0:
            log.debug("Empty graph, skipping save")
            return True
        
        try:
            # Create directory if needed
            os.makedirs(os.path.dirname(KG_PERSIST_PATH), exist_ok=True)
            
            # Create a copy for serialization (convert lists to JSON strings)
            import json
            graph_copy = self.graph.copy()
            for node, data in graph_copy.nodes(data=True):
                for key, value in list(data.items()):
                    if isinstance(value, (list, dict)):
                        # Convert complex types to JSON strings for GraphML compatibility
                        data[key] = json.dumps(value)
            
            # Save as GraphML
            nx.write_graphml(graph_copy, KG_PERSIST_PATH)
            log.info(f"Saved knowledge graph to {KG_PERSIST_PATH}")
            return True
        except Exception as e:
            log.error(f"Failed to save knowledge graph: {e}")
            return False
    
    def add_concept(
        self,
        concept: str,
        concept_type: str = "CONCEPT",
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a concept as a node to the graph.
        
        Args:
            concept: Concept text (normalized)
            concept_type: Type of concept (PERSON, TECH, etc.)
            metadata: Additional metadata
            
        Returns:
            True if added, False if already exists or limit reached
        """
        if not concept or not concept.strip():
            return False
        
        concept = concept.strip()
        
        # Check node limit
        if self.graph.number_of_nodes() >= KG_MAX_NODES and concept not in self.graph:
            log.warning(f"Maximum nodes ({KG_MAX_NODES}) reached")
            return False
        
        # Check if exists
        if self.graph.has_node(concept):
            # Update metadata if provided
            if metadata:
                node_data = self.graph.nodes[concept]
                node_data.update(metadata)
                node_data["updated_at"] = int(time.time())
            return True
        
        # Add node with metadata
        node_data = {
            "type": concept_type,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        if metadata:
            node_data.update(metadata)
        
        self.graph.add_node(concept, **node_data)
        self._last_modified = time.time()
        
        log.debug(f"Added concept: {concept} ({concept_type})")
        return True
    
    def add_relationship(
        self,
        source: str,
        target: str,
        relation_type: str = "related_to",
        weight: float = 1.0,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Add a relationship (edge) between two concepts.
        
        Args:
            source: Source concept
            target: Target concept
            relation_type: Type of relationship
            weight: Relationship weight (0-1)
            metadata: Additional metadata
            
        Returns:
            True if added, False otherwise
        """
        if not source or not target:
            return False
        
        source = source.strip()
        target = target.strip()
        
        # Ensure both concepts exist as nodes
        if not self.graph.has_node(source):
            self.add_concept(source)
        if not self.graph.has_node(target):
            self.add_concept(target)
        
        # Check edge limit per node
        if self.graph.out_degree(source) >= KG_MAX_EDGES_PER_NODE:
            log.warning(f"Maximum edges per node ({KG_MAX_EDGES_PER_NODE}) reached for {source}")
            return False
        
        # Add or update edge
        edge_data = {
            "relation": relation_type,
            "weight": weight,
            "created_at": int(time.time()),
        }
        if metadata:
            edge_data.update(metadata)
        
        self.graph.add_edge(source, target, **edge_data)
        self._last_modified = time.time()
        
        log.debug(f"Added relationship: {source} --[{relation_type}:{weight:.2f}]--> {target}")
        return True
    
    def compute_semantic_similarity(self, concept1: str, concept2: str) -> float:
        """
        Compute semantic similarity between two concepts using embeddings.
        
        Args:
            concept1: First concept
            concept2: Second concept
            
        Returns:
            Similarity score (0-1), or 0 if embedding not available
        """
        embed_fn = _get_embedding_function()
        if embed_fn is None:
            return 0.0
        
        try:
            np = _get_numpy()
            if np is None:
                return 0.0
            
            # Get embeddings
            embeddings = embed_fn.encode([concept1, concept2])
            
            # Compute cosine similarity
            similarity = float(np.dot(embeddings[0], embeddings[1]) / 
                             (np.linalg.norm(embeddings[0]) * np.linalg.norm(embeddings[1])))
            
            return max(0.0, min(1.0, similarity))
        except Exception as e:
            log.warning(f"Failed to compute similarity: {e}")
            return 0.0
    
    def infer_relationships(
        self,
        concept: str,
        candidates: List[str],
        threshold: float = KG_SIMILARITY_THRESHOLD
    ) -> List[Tuple[str, float]]:
        """
        Infer relationships based on semantic similarity.
        
        Args:
            concept: Source concept
            candidates: List of candidate concepts to relate
            threshold: Minimum similarity threshold
            
        Returns:
            List of (candidate, similarity) tuples above threshold
        """
        relationships = []
        
        for candidate in candidates:
            if candidate == concept:
                continue
            
            similarity = self.compute_semantic_similarity(concept, candidate)
            if similarity >= threshold:
                relationships.append((candidate, similarity))
        
        # Sort by similarity (descending)
        relationships.sort(key=lambda x: x[1], reverse=True)
        return relationships
    
    def find_related(
        self,
        concept: str,
        depth: int = 2,
        max_results: int = 10
    ) -> List[RelatedConcept]:
        """
        Find related concepts within specified depth.
        
        Args:
            concept: Source concept
            depth: Maximum graph distance
            max_results: Maximum number of results
            
        Returns:
            List of RelatedConcept objects
        """
        nx = _get_networkx()
        if not self.graph.has_node(concept):
            log.debug(f"Concept not in graph: {concept}")
            return []
        
        related = []
        visited = {concept}
        
        try:
            # BFS to find related concepts
            for current_depth in range(1, depth + 1):
                for node in list(visited):
                    # Out edges (concepts this node relates to)
                    for neighbor in self.graph.neighbors(node):
                        if neighbor in visited:
                            continue
                        
                        edge_data = self.graph.edges[node, neighbor]
                        related.append(RelatedConcept(
                            concept=neighbor,
                            relation_type=edge_data.get("relation", "related_to"),
                            weight=edge_data.get("weight", 1.0),
                            distance=current_depth
                        ))
                        visited.add(neighbor)
                    
                    # In edges (concepts that relate to this node)
                    for predecessor in self.graph.predecessors(node):
                        if predecessor in visited:
                            continue
                        
                        edge_data = self.graph.edges[predecessor, node]
                        related.append(RelatedConcept(
                            concept=predecessor,
                            relation_type=edge_data.get("relation", "related_to"),
                            weight=edge_data.get("weight", 1.0),
                            distance=current_depth
                        ))
                        visited.add(predecessor)
        except Exception as e:
            log.error(f"Error finding related concepts: {e}")
        
        # Sort by weight (descending) and distance (ascending)
        related.sort(key=lambda x: (-x.weight, x.distance))
        return related[:max_results]
    
    def get_context(self, concept: str) -> str:
        """
        Get full context for a concept with its relationships.
        
        Args:
            concept: Concept to get context for
            
        Returns:
            Formatted context string
        """
        if not self.graph.has_node(concept):
            return f"Concept '{concept}' not found in knowledge graph."
        
        # Get node metadata
        node_data = self.graph.nodes[concept]
        concept_type = node_data.get("type", "CONCEPT")
        
        # Get related concepts
        related = self.find_related(concept, depth=2, max_results=20)
        
        # Build context string
        context_lines = [
            f"📊 CONCEPT: {concept} ({concept_type})",
            "",
            "🔗 RELATIONSHIPS:",
        ]
        
        if not related:
            context_lines.append("  No relationships found.")
        else:
            # Group by distance
            by_distance = {}
            for rel in related:
                if rel.distance not in by_distance:
                    by_distance[rel.distance] = []
                by_distance[rel.distance].append(rel)
            
            for distance in sorted(by_distance.keys()):
                context_lines.append(f"\n  Distance {distance}:")
                for rel in by_distance[distance]:
                    context_lines.append(
                        f"    - {rel.concept} [{rel.relation_type}] (weight: {rel.weight:.2f})"
                    )
        
        return "\n".join(context_lines)
    
    def visualize_subgraph(
        self,
        concept: str,
        depth: int = 1,
        max_nodes: int = 15
    ) -> str:
        """
        Generate ASCII art visualization of subgraph around concept.
        
        Args:
            concept: Center concept
            depth: Maximum distance from center
            max_nodes: Maximum nodes to include
            
        Returns:
            ASCII art string
        """
        if not self.graph.has_node(concept):
            return f"Concept '{concept}' not found in knowledge graph."
        
        # Get related concepts
        related = self.find_related(concept, depth=depth, max_results=max_nodes - 1)
        
        if not related:
            return f"🔵 {concept}\n  (no relationships)"
        
        # Build ASCII visualization
        lines = [f"🔵 {concept} (center)"]
        
        # Group by distance
        by_distance = {}
        for rel in related:
            if rel.distance not in by_distance:
                by_distance[rel.distance] = []
            by_distance[rel.distance].append(rel)
        
        for distance in sorted(by_distance.keys()):
            lines.append(f"\n  └─ Distance {distance}:")
            items = by_distance[distance]
            for i, rel in enumerate(items):
                is_last = (i == len(items) - 1)
                prefix = "     └─" if is_last else "     ├─"
                lines.append(
                    f"{prefix} {rel.concept} [{rel.relation_type}] (w={rel.weight:.2f})"
                )
        
        return "\n".join(lines)
    
    def get_stats(self) -> Dict[str, Any]:
        """Get knowledge graph statistics."""
        nx = _get_networkx()
        
        stats = {
            "nodes": self.graph.number_of_nodes(),
            "edges": self.graph.number_of_edges(),
            "last_modified": self._last_modified,
        }
        
        # Node types distribution
        type_counts = {}
        for node, data in self.graph.nodes(data=True):
            node_type = data.get("type", "UNKNOWN")
            type_counts[node_type] = type_counts.get(node_type, 0) + 1
        stats["node_types"] = type_counts
        
        # Average degree
        if stats["nodes"] > 0:
            stats["avg_degree"] = stats["edges"] / stats["nodes"]
        else:
            stats["avg_degree"] = 0.0
        
        return stats
    
    def cleanup_old_concepts(self, days: int = 365) -> int:
        """
        Remove concepts older than specified days with no edges.
        
        Args:
            days: Age threshold in days
            
        Returns:
            Number of concepts removed
        """
        threshold = int(time.time()) - (days * 86400)
        to_remove = []
        
        for node, data in self.graph.nodes(data=True):
            created_at = data.get("created_at", 0)
            # Remove if old and isolated (no edges)
            if created_at < threshold and self.graph.degree(node) == 0:
                to_remove.append(node)
        
        for node in to_remove:
            self.graph.remove_node(node)
        
        if to_remove:
            self._last_modified = time.time()
            log.info(f"Cleaned up {len(to_remove)} old isolated concepts")
        
        return len(to_remove)
    
    def find_related_multi_hop(
        self,
        concept: str,
        max_depth: int = 3,
        max_results: int = 20
    ) -> Dict[int, List[RelatedConcept]]:
        """
        Find related concepts at multiple depths (1-hop, 2-hop, 3-hop).
        Results are grouped by distance for ranking.
        
        Args:
            concept: Source concept
            max_depth: Maximum graph distance (1-3 recommended)
            max_results: Maximum total results across all hops
            
        Returns:
            Dict mapping distance (1, 2, 3) to list of RelatedConcept objects
        """
        nx = _get_networkx()
        if not self.graph.has_node(concept):
            log.debug(f"Concept not in graph: {concept}")
            return {}
        
        results_by_hop: Dict[int, List[RelatedConcept]] = {}
        visited = {concept}
        current_level = {concept}
        
        try:
            for depth in range(1, min(max_depth + 1, 4)):  # Cap at 3 hops
                next_level = set()
                hop_results = []
                
                for node in current_level:
                    # Out edges
                    for neighbor in self.graph.neighbors(node):
                        if neighbor not in visited:
                            edge_data = self.graph.edges[node, neighbor]
                            hop_results.append(RelatedConcept(
                                concept=neighbor,
                                relation_type=edge_data.get("relation", "related_to"),
                                weight=edge_data.get("weight", 1.0),
                                distance=depth
                            ))
                            visited.add(neighbor)
                            next_level.add(neighbor)
                    
                    # In edges
                    for predecessor in self.graph.predecessors(node):
                        if predecessor not in visited:
                            edge_data = self.graph.edges[predecessor, node]
                            hop_results.append(RelatedConcept(
                                concept=predecessor,
                                relation_type=edge_data.get("relation", "related_to"),
                                weight=edge_data.get("weight", 1.0),
                                distance=depth
                            ))
                            visited.add(predecessor)
                            next_level.add(predecessor)
                
                # Sort by weight (descending)
                hop_results.sort(key=lambda x: x.weight, reverse=True)
                results_by_hop[depth] = hop_results
                
                current_level = next_level
                
                # Early termination if we have enough results
                total_results = sum(len(v) for v in results_by_hop.values())
                if total_results >= max_results:
                    break
        
        except Exception as e:
            log.error(f"Error in multi-hop traversal: {e}")
        
        return results_by_hop
    
    def detect_communities(self, min_cluster_size: int = 3) -> Dict[str, int]:
        """
        Detect concept clusters using Louvain community detection.
        
        Args:
            min_cluster_size: Minimum number of nodes in a valid cluster
            
        Returns:
            Dict mapping concept name to cluster ID
        """
        nx = _get_networkx()
        
        # Check if we have enough nodes
        if self.graph.number_of_nodes() < min_cluster_size:
            log.debug(f"Not enough nodes ({self.graph.number_of_nodes()}) for clustering")
            return {}
        
        try:
            # Try to import community detection
            try:
                import networkx.algorithms.community as nx_comm
            except ImportError:
                log.warning("NetworkX community module not available")
                return {}
            
            # Convert directed graph to undirected for community detection
            undirected = self.graph.to_undirected()
            
            # Run Louvain algorithm
            communities = nx_comm.louvain_communities(undirected, seed=42)
            
            # Build concept -> cluster mapping
            concept_to_cluster = {}
            valid_cluster_id = 0
            
            for cluster_id, community in enumerate(communities):
                # Only keep clusters above minimum size
                if len(community) >= min_cluster_size:
                    for concept in community:
                        concept_to_cluster[concept] = valid_cluster_id
                    valid_cluster_id += 1
            
            log.info(f"Detected {valid_cluster_id} clusters from {len(communities)} communities")
            return concept_to_cluster
            
        except Exception as e:
            log.error(f"Community detection failed: {e}")
            return {}
    
    def get_cluster_info(self, cluster_id: int, concept_clusters: Dict[str, int]) -> Dict[str, Any]:
        """
        Get information about a specific cluster.
        
        Args:
            cluster_id: The cluster ID
            concept_clusters: Mapping from concept to cluster ID
            
        Returns:
            Dict with cluster metadata
        """
        # Get all concepts in this cluster
        cluster_concepts = [
            concept for concept, cid in concept_clusters.items() 
            if cid == cluster_id
        ]
        
        if not cluster_concepts:
            return {"cluster_id": cluster_id, "size": 0, "concepts": []}
        
        # Count concept types in cluster
        type_counts = {}
        for concept in cluster_concepts:
            if self.graph.has_node(concept):
                node_data = self.graph.nodes[concept]
                concept_type = node_data.get("type", "UNKNOWN")
                type_counts[concept_type] = type_counts.get(concept_type, 0) + 1
        
        # Determine dominant type (cluster label)
        dominant_type = max(type_counts.items(), key=lambda x: x[1])[0] if type_counts else "UNKNOWN"
        
        # Sample key concepts (sorted by degree centrality)
        degrees = {concept: self.graph.degree(concept) for concept in cluster_concepts}
        key_concepts = sorted(cluster_concepts, key=lambda c: degrees[c], reverse=True)[:5]
        
        return {
            "cluster_id": cluster_id,
            "size": len(cluster_concepts),
            "dominant_type": dominant_type,
            "type_distribution": type_counts,
            "key_concepts": key_concepts,
            "concepts": cluster_concepts,
        }
    
    def update_concept_version(
        self,
        concept: str,
        new_data: Dict[str, Any],
        version_limit: int = 5
    ) -> bool:
        """
        Update concept with versioned changes. Stores change history.
        
        Args:
            concept: Concept name
            new_data: New/updated attributes
            version_limit: Maximum number of versions to keep
            
        Returns:
            True if updated successfully
        """
        if not self.graph.has_node(concept):
            log.warning(f"Cannot version non-existent concept: {concept}")
            return False
        
        node_data = self.graph.nodes[concept]
        
        # Get or initialize version history
        if "version_history" not in node_data:
            node_data["version_history"] = []
        
        # Create version snapshot
        version = {
            "timestamp": int(time.time()),
            "changes": new_data.copy(),
        }
        
        # Add to history
        node_data["version_history"].append(version)
        
        # Limit history size
        if len(node_data["version_history"]) > version_limit:
            node_data["version_history"] = node_data["version_history"][-version_limit:]
        
        # Apply changes to current node
        node_data.update(new_data)
        node_data["updated_at"] = int(time.time())
        
        self._last_modified = time.time()
        log.debug(f"Updated concept version: {concept} (total versions: {len(node_data['version_history'])})")
        
        return True
    
    def get_concept_evolution(self, concept: str) -> List[Dict[str, Any]]:
        """
        Get evolution history of a concept.
        
        Args:
            concept: Concept name
            
        Returns:
            List of version snapshots (oldest to newest)
        """
        if not self.graph.has_node(concept):
            return []
        
        node_data = self.graph.nodes[concept]
        return node_data.get("version_history", [])
    
    def suggest_related_topics(
        self,
        current_topic: str,
        top_k: int = 5,
        use_centrality: bool = True
    ) -> List[str]:
        """
        Suggest related topics based on graph structure.
        Uses degree centrality or PageRank to find important related concepts.
        
        Args:
            current_topic: Starting concept
            top_k: Number of suggestions to return
            use_centrality: Use degree centrality (faster) vs PageRank
            
        Returns:
            List of suggested concept names
        """
        nx = _get_networkx()
        
        if not self.graph.has_node(current_topic):
            log.debug(f"Topic not in graph: {current_topic}")
            return []
        
        try:
            # Get directly related concepts first
            related = self.find_related(current_topic, depth=2, max_results=top_k * 3)
            related_concepts = {r.concept for r in related}
            
            # Calculate importance scores
            if use_centrality:
                # Degree centrality (faster, good enough for most cases)
                scores = {
                    node: self.graph.degree(node)
                    for node in related_concepts
                }
            else:
                # PageRank (slower but more accurate for complex graphs)
                try:
                    pagerank = nx.pagerank(self.graph, max_iter=50)
                    scores = {
                        node: pagerank.get(node, 0.0)
                        for node in related_concepts
                    }
                except Exception as e:
                    log.warning(f"PageRank failed, falling back to centrality: {e}")
                    scores = {
                        node: self.graph.degree(node)
                        for node in related_concepts
                    }
            
            # Sort by importance
            sorted_suggestions = sorted(
                scores.items(),
                key=lambda x: x[1],
                reverse=True
            )
            
            return [concept for concept, _ in sorted_suggestions[:top_k]]
            
        except Exception as e:
            log.error(f"Error generating suggestions: {e}")
            return []


# === Singleton Instance ===
_kg_instance: Optional[KnowledgeGraph] = None


def get_knowledge_graph() -> Optional[KnowledgeGraph]:
    """
    Get or create KnowledgeGraph singleton.
    
    Returns:
        KnowledgeGraph instance or None if disabled
    """
    global _kg_instance
    
    if not ENABLE_KNOWLEDGE_GRAPH:
        return None
    
    if _kg_instance is None:
        try:
            _kg_instance = KnowledgeGraph()
        except Exception as e:
            log.error(f"Failed to initialize KnowledgeGraph: {e}")
            return None
    
    return _kg_instance


# === Test ===
if __name__ == "__main__":
    print("🧪 Testing Knowledge Graph")
    print("=" * 60)
    
    kg = get_knowledge_graph()
    if kg is None:
        print("❌ Knowledge Graph not available")
        exit(1)
    
    # Add concepts
    kg.add_concept("Python", "TECH")
    kg.add_concept("FastAPI", "TECH")
    kg.add_concept("ChromaDB", "TECH")
    kg.add_concept("spaCy", "TECH")
    kg.add_concept("NetworkX", "TECH")
    
    # Add relationships
    kg.add_relationship("FastAPI", "Python", "uses", 0.95)
    kg.add_relationship("ChromaDB", "Python", "uses", 0.90)
    kg.add_relationship("spaCy", "Python", "uses", 0.92)
    kg.add_relationship("NetworkX", "Python", "uses", 0.88)
    
    # Infer semantic relationships
    similarity = kg.compute_semantic_similarity("FastAPI", "ChromaDB")
    print(f"\n🔍 Semantic similarity (FastAPI <-> ChromaDB): {similarity:.3f}")
    
    if similarity >= KG_SIMILARITY_THRESHOLD:
        kg.add_relationship("FastAPI", "ChromaDB", "related_to", similarity)
    
    # Find related concepts
    print(f"\n🔗 Concepts related to 'Python':")
    related = kg.find_related("Python", depth=2)
    for rel in related:
        print(f"  - {rel.concept} [{rel.relation_type}] (w={rel.weight:.2f}, d={rel.distance})")
    
    # Get context
    print(f"\n{kg.get_context('Python')}")
    
    # Visualize
    print(f"\n📊 Visualization:")
    print(kg.visualize_subgraph("Python", depth=2))
    
    # Stats
    stats = kg.get_stats()
    print(f"\n📈 Stats: {stats}")
    
    # Save
    kg.save_graph()
    print(f"\n✅ Test complete! Graph saved to {KG_PERSIST_PATH}")
