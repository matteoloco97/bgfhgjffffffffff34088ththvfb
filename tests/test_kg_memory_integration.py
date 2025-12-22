#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_kg_memory_integration.py — Tests for Knowledge Graph Memory Integration

Comprehensive tests for graph-enhanced memory retrieval system:
- Multi-hop traversal with ranking
- Concept clustering
- Evolution tracking
- Graph-based topic suggestions
"""

import sys
import os
import unittest
import tempfile
from typing import List, Dict, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables
os.environ["ENABLE_KNOWLEDGE_GRAPH"] = "1"
os.environ["KG_SIMILARITY_THRESHOLD"] = "0.6"
os.environ["USER_PROFILE_ENABLED"] = "1"
os.environ["EPISODIC_MEMORY_ENABLED"] = "1"
os.environ["SPACY_MODEL"] = "en_core_web_sm"

# Create temp directories
test_dir = tempfile.mkdtemp()
os.environ["KG_PERSIST_PATH"] = os.path.join(test_dir, "test_graph.graphml")
os.environ["CHROMA_PERSIST_DIR"] = os.path.join(test_dir, "chroma_test")

from core.knowledge_graph import (
    KnowledgeGraph,
    get_knowledge_graph,
)
from core.user_profile_memory import (
    query_user_profile,
    save_user_profile_fact,
)


class TestGraphEnhancedMemory(unittest.TestCase):
    """Test graph-enhanced memory retrieval."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test fixtures."""
        cls.kg = get_knowledge_graph()
        cls.test_user_id = "test_graph_user"
        
        # Build a test knowledge graph
        cls._build_test_graph()
        
        # Save some test facts
        cls._save_test_facts()
    
    @classmethod
    def _build_test_graph(cls):
        """Build a test knowledge graph with concepts and relationships."""
        if not cls.kg:
            return
        
        # Add Python ecosystem concepts
        cls.kg.add_concept("Python", "TECH")
        cls.kg.add_concept("FastAPI", "TECH")
        cls.kg.add_concept("Django", "TECH")
        cls.kg.add_concept("Flask", "TECH")
        cls.kg.add_concept("NumPy", "TECH")
        cls.kg.add_concept("Pandas", "TECH")
        cls.kg.add_concept("Machine Learning", "TECH")
        cls.kg.add_concept("Data Science", "TECH")
        
        # Add relationships (1-hop from Python)
        cls.kg.add_relationship("FastAPI", "Python", "uses", 0.95)
        cls.kg.add_relationship("Django", "Python", "uses", 0.93)
        cls.kg.add_relationship("Flask", "Python", "uses", 0.92)
        cls.kg.add_relationship("NumPy", "Python", "uses", 0.90)
        cls.kg.add_relationship("Pandas", "Python", "uses", 0.88)
        
        # Add 2-hop relationships
        cls.kg.add_relationship("Pandas", "NumPy", "depends_on", 0.85)
        cls.kg.add_relationship("Machine Learning", "NumPy", "uses", 0.80)
        cls.kg.add_relationship("Machine Learning", "Pandas", "uses", 0.82)
        cls.kg.add_relationship("Data Science", "Pandas", "uses", 0.78)
        cls.kg.add_relationship("Data Science", "Machine Learning", "includes", 0.75)
        
        print(f"✓ Test graph built: {cls.kg.graph.number_of_nodes()} nodes, {cls.kg.graph.number_of_edges()} edges")
    
    @classmethod
    def _save_test_facts(cls):
        """Save test facts to user profile."""
        facts = [
            "I work with Python for web development",
            "I use FastAPI for building APIs",
            "I'm learning Machine Learning",
            "I prefer Pandas for data analysis",
        ]
        
        for fact in facts:
            save_user_profile_fact(
                user_id=cls.test_user_id,
                fact_text=fact,
                category="project"
            )
        
        print(f"✓ Saved {len(facts)} test facts")
    
    def test_direct_match_retrieval(self):
        """Test direct semantic match without graph traversal."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        results = query_user_profile(
            user_id=self.test_user_id,
            query_text="Python web development",
            top_k=3,
            use_graph_traversal=False  # Disable graph
        )
        
        self.assertGreater(len(results), 0, "Should find direct matches")
        
        # All results should be direct matches
        for result in results:
            self.assertEqual(result.get("hop_distance"), 0, "Should be direct match")
            self.assertEqual(result.get("match_type"), "direct", "Should be direct match type")
    
    def test_graph_enhanced_retrieval(self):
        """Test graph-enhanced retrieval with multi-hop traversal."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        results = query_user_profile(
            user_id=self.test_user_id,
            query_text="NumPy arrays",  # Related to Python via graph
            top_k=5,
            use_graph_traversal=True,  # Enable graph
            max_graph_hops=2
        )
        
        self.assertGreater(len(results), 0, "Should find results via graph traversal")
        
        # Should have both direct and graph-expanded results
        has_direct = any(r.get("hop_distance") == 0 for r in results)
        has_graph = any(r.get("hop_distance") > 0 for r in results)
        
        print(f"\nGraph-enhanced results:")
        for r in results:
            print(f"  - hop={r.get('hop_distance')}, sim={r.get('similarity', 0):.3f}, "
                  f"type={r.get('match_type')}, text={r.get('text', '')[:50]}...")
        
        # We expect some graph-expanded results since we're querying for NumPy
        # which is related to Python concepts in user facts
        if has_graph:
            print("✓ Found graph-expanded results")
    
    def test_hop_distance_ranking(self):
        """Test that results are ranked by hop distance (direct > 1-hop > 2-hop)."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        results = query_user_profile(
            user_id=self.test_user_id,
            query_text="Data Science tools",
            top_k=10,
            use_graph_traversal=True,
            max_graph_hops=3
        )
        
        if len(results) < 2:
            self.skipTest("Not enough results to test ranking")
        
        # Check that results are sorted by hop distance (ascending)
        hop_distances = [r.get("hop_distance", 0) for r in results]
        
        # Within same hop distance, should be sorted by similarity
        for i in range(len(results) - 1):
            curr_hop = results[i].get("hop_distance", 0)
            next_hop = results[i + 1].get("hop_distance", 0)
            
            # Lower hop distance should come first
            self.assertLessEqual(curr_hop, next_hop,
                               f"Result {i} should have lower or equal hop distance than {i+1}")
        
        print(f"✓ Results properly ranked by hop distance: {hop_distances}")
    
    def test_cluster_detection(self):
        """Test concept clustering with Louvain algorithm."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        # Detect communities
        concept_clusters = self.kg.detect_communities(min_cluster_size=2)
        
        if not concept_clusters:
            self.skipTest("No clusters detected (graph might be too small)")
        
        # Should have at least one cluster
        self.assertGreater(len(concept_clusters), 0, "Should detect at least one cluster")
        
        # Get cluster IDs
        cluster_ids = set(concept_clusters.values())
        
        print(f"\n✓ Detected {len(cluster_ids)} clusters:")
        for cluster_id in sorted(cluster_ids):
            cluster_info = self.kg.get_cluster_info(cluster_id, concept_clusters)
            print(f"  - Cluster {cluster_id}: {cluster_info['size']} concepts, "
                  f"dominant type: {cluster_info['dominant_type']}")
            print(f"    Key concepts: {', '.join(cluster_info['key_concepts'][:3])}")
    
    def test_cluster_context_in_results(self):
        """Test that cluster context is added to retrieval results."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        results = query_user_profile(
            user_id=self.test_user_id,
            query_text="Python programming",
            top_k=5,
            use_graph_traversal=True,
            max_graph_hops=2
        )
        
        # Check if any results have cluster context
        has_cluster_context = any("cluster_context" in r for r in results)
        
        if has_cluster_context:
            print("\n✓ Found results with cluster context:")
            for r in results:
                if "cluster_context" in r:
                    print(f"  - {r.get('cluster_context')}")
        else:
            print("ℹ No cluster context (graph might be too small for clustering)")
    
    def test_concept_evolution_tracking(self):
        """Test concept evolution tracking over time."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        # Add a concept and update it multiple times
        test_concept = "TestConcept"
        self.kg.add_concept(test_concept, "TEST", {"version": "1.0"})
        
        # Track evolution
        self.kg.update_concept_version(
            test_concept,
            {"version": "1.1", "feature": "added_caching"}
        )
        
        self.kg.update_concept_version(
            test_concept,
            {"version": "1.2", "feature": "improved_performance"}
        )
        
        # Get evolution history
        history = self.kg.get_concept_evolution(test_concept)
        
        self.assertEqual(len(history), 2, "Should have 2 version updates")
        
        print(f"\n✓ Concept evolution tracked:")
        for i, version in enumerate(history):
            print(f"  - Version {i+1}: {version.get('changes', {})}")
    
    def test_topic_suggestions(self):
        """Test graph-based topic suggestions."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        # Get suggestions for Python
        suggestions = self.kg.suggest_related_topics(
            current_topic="Python",
            top_k=5,
            use_centrality=True
        )
        
        self.assertGreater(len(suggestions), 0, "Should suggest related topics")
        
        print(f"\n✓ Topic suggestions for 'Python':")
        for topic in suggestions:
            print(f"  - {topic}")
        
        # Test with PageRank (slower but more accurate)
        suggestions_pr = self.kg.suggest_related_topics(
            current_topic="Python",
            top_k=5,
            use_centrality=False  # Use PageRank
        )
        
        print(f"\n✓ Topic suggestions (PageRank) for 'Python':")
        for topic in suggestions_pr:
            print(f"  - {topic}")
    
    def test_multi_hop_traversal(self):
        """Test multi-hop graph traversal returns correct structure."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        # Test multi-hop from Python
        results_by_hop = self.kg.find_related_multi_hop(
            concept="Python",
            max_depth=3,
            max_results=20
        )
        
        self.assertIsInstance(results_by_hop, dict, "Should return dict of results by hop")
        
        # Check structure
        for hop_distance, concepts in results_by_hop.items():
            self.assertIsInstance(hop_distance, int, "Hop distance should be int")
            self.assertGreater(hop_distance, 0, "Hop distance should be > 0")
            self.assertIsInstance(concepts, list, "Concepts should be a list")
            
            for concept in concepts:
                self.assertEqual(concept.distance, hop_distance, 
                               "Concept distance should match hop distance")
        
        print(f"\n✓ Multi-hop traversal from 'Python':")
        for hop, concepts in sorted(results_by_hop.items()):
            print(f"  - {hop}-hop: {len(concepts)} concepts")
            for c in concepts[:3]:  # Show first 3
                print(f"    • {c.concept} [{c.relation_type}] (weight={c.weight:.2f})")
    
    def test_graph_stats(self):
        """Test knowledge graph statistics."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        stats = self.kg.get_stats()
        
        self.assertIn("nodes", stats)
        self.assertIn("edges", stats)
        self.assertIn("node_types", stats)
        self.assertIn("avg_degree", stats)
        
        self.assertGreater(stats["nodes"], 0, "Should have nodes")
        
        print(f"\n✓ Knowledge Graph Stats:")
        print(f"  - Nodes: {stats['nodes']}")
        print(f"  - Edges: {stats['edges']}")
        print(f"  - Average degree: {stats['avg_degree']:.2f}")
        print(f"  - Node types: {stats['node_types']}")
    
    def test_graph_enrichment_flag(self):
        """Test that graph_enriched flag is set correctly."""
        if not self.kg:
            self.skipTest("Knowledge graph not available")
        
        results = query_user_profile(
            user_id=self.test_user_id,
            query_text="Python development",
            top_k=5,
            use_graph_traversal=True
        )
        
        if len(results) > 0:
            # At least some results should be marked as graph enriched
            has_flag = any(r.get("graph_enriched") for r in results)
            self.assertTrue(has_flag, "Results should have graph_enriched flag")
            
            print("✓ Results properly marked with graph_enriched flag")


class TestMemoryContextBuilder(unittest.TestCase):
    """Test memory context builder with graph integration."""
    
    def test_memory_context_with_graph(self):
        """Test that memory context builder uses graph traversal."""
        try:
            from core.memory_context_builder import build_memory_context
        except ImportError:
            self.skipTest("Memory context builder not available")
        
        test_user_id = "test_context_user"
        
        # Save a test fact
        save_user_profile_fact(
            user_id=test_user_id,
            fact_text="I work with Python and FastAPI",
            category="project"
        )
        
        # Build context
        context = build_memory_context(
            user_id=test_user_id,
            query="What do you know about my tech stack?",
            query_lower="what do you know about my tech stack?",
            conversation_id="test_conv",
            profile_top_k=5,
            max_tokens=800
        )
        
        self.assertIn("context_text", context)
        self.assertIn("profile_facts", context)
        
        if context["profile_facts"]:
            print(f"\n✓ Memory context built with {len(context['profile_facts'])} facts")
            print(f"  Context preview: {context['context_text'][:200]}...")


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add tests
    suite.addTests(loader.loadTestsFromTestCase(TestGraphEnhancedMemory))
    suite.addTests(loader.loadTestsFromTestCase(TestMemoryContextBuilder))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    print("=" * 70)
    print("Knowledge Graph Memory Integration Tests")
    print("=" * 70)
    
    success = run_tests()
    
    print("\n" + "=" * 70)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed")
    print("=" * 70)
    
    sys.exit(0 if success else 1)
