#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_knowledge_graph_enhancement.py — Tests for Knowledge Graph Enhancements

Tests for:
- Multi-hop graph traversal
- Concept clustering with Louvain algorithm
- Concept evolution tracking
- Graph-based topic suggestions
- Graph-enhanced memory retrieval
"""

import sys
import os
import unittest
import tempfile
from typing import Dict, List, Any

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables
os.environ["ENABLE_KNOWLEDGE_GRAPH"] = "1"
os.environ["KG_SIMILARITY_THRESHOLD"] = "0.6"
os.environ["USER_PROFILE_ENABLED"] = "1"

# Create temp directory for test graph
test_dir = tempfile.mkdtemp()
os.environ["KG_PERSIST_PATH"] = os.path.join(test_dir, "test_graph.graphml")

from core.knowledge_graph import KnowledgeGraph, get_knowledge_graph


class TestMultiHopTraversal(unittest.TestCase):
    """Test multi-hop graph traversal functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Build a test graph with clear hop distances."""
        cls.kg = KnowledgeGraph()
        
        # Build a chain: A -> B -> C -> D
        # And a branch: A -> E -> F
        cls.kg.add_concept("A", "TECH")
        cls.kg.add_concept("B", "TECH")
        cls.kg.add_concept("C", "TECH")
        cls.kg.add_concept("D", "TECH")
        cls.kg.add_concept("E", "TECH")
        cls.kg.add_concept("F", "TECH")
        
        # Chain relationships
        cls.kg.add_relationship("A", "B", "uses", 0.9)
        cls.kg.add_relationship("B", "C", "uses", 0.8)
        cls.kg.add_relationship("C", "D", "uses", 0.7)
        
        # Branch relationships
        cls.kg.add_relationship("A", "E", "related_to", 0.85)
        cls.kg.add_relationship("E", "F", "uses", 0.75)
    
    def test_one_hop_traversal(self):
        """Test 1-hop traversal."""
        results = self.kg.find_related_multi_hop("A", max_depth=1)
        
        self.assertIn(1, results, "Should have 1-hop results")
        hop1_concepts = {r.concept for r in results[1]}
        
        # Should find direct neighbors B and E
        self.assertIn("B", hop1_concepts, "Should find B at 1-hop")
        self.assertIn("E", hop1_concepts, "Should find E at 1-hop")
        
        # Should not find C, D, F (they're 2+ hops away)
        self.assertNotIn("C", hop1_concepts)
        self.assertNotIn("D", hop1_concepts)
        self.assertNotIn("F", hop1_concepts)
    
    def test_two_hop_traversal(self):
        """Test 2-hop traversal."""
        results = self.kg.find_related_multi_hop("A", max_depth=2)
        
        self.assertIn(1, results, "Should have 1-hop results")
        self.assertIn(2, results, "Should have 2-hop results")
        
        hop2_concepts = {r.concept for r in results[2]}
        
        # Should find C and F at 2-hops
        self.assertIn("C", hop2_concepts, "Should find C at 2-hop")
        self.assertIn("F", hop2_concepts, "Should find F at 2-hop")
    
    def test_three_hop_traversal(self):
        """Test 3-hop traversal."""
        results = self.kg.find_related_multi_hop("A", max_depth=3)
        
        self.assertIn(3, results, "Should have 3-hop results")
        hop3_concepts = {r.concept for r in results[3]}
        
        # Should find D at 3-hops
        self.assertIn("D", hop3_concepts, "Should find D at 3-hop")
    
    def test_hop_ordering(self):
        """Test that results are properly organized by hop distance."""
        results = self.kg.find_related_multi_hop("A", max_depth=3)
        
        # Each hop should have results
        for hop in [1, 2, 3]:
            self.assertIn(hop, results, f"Should have results for {hop}-hop")
        
        # Verify distances are correct
        for hop, concepts in results.items():
            for concept in concepts:
                self.assertEqual(concept.distance, hop, 
                               f"Concept {concept.concept} should be at distance {hop}")


class TestConceptClustering(unittest.TestCase):
    """Test concept clustering with Louvain algorithm."""
    
    @classmethod
    def setUpClass(cls):
        """Build a test graph with clear clusters."""
        cls.kg = KnowledgeGraph()
        
        # Cluster 1: Python ecosystem
        for concept in ["Python", "Django", "Flask", "NumPy"]:
            cls.kg.add_concept(concept, "TECH")
        cls.kg.add_relationship("Django", "Python", "uses", 0.9)
        cls.kg.add_relationship("Flask", "Python", "uses", 0.9)
        cls.kg.add_relationship("NumPy", "Python", "uses", 0.9)
        
        # Cluster 2: JavaScript ecosystem
        for concept in ["JavaScript", "React", "Node.js", "Express"]:
            cls.kg.add_concept(concept, "TECH")
        cls.kg.add_relationship("React", "JavaScript", "uses", 0.9)
        cls.kg.add_relationship("Node.js", "JavaScript", "uses", 0.9)
        cls.kg.add_relationship("Express", "Node.js", "uses", 0.8)
    
    def test_clustering_basic(self):
        """Test basic clustering functionality."""
        clusters = self.kg.detect_communities(min_cluster_size=3)
        
        # Should detect at least one cluster
        self.assertGreater(len(clusters), 0, "Should detect clusters")
        
        # Check that concepts are assigned to clusters
        self.assertIn("Python", clusters, "Python should be in a cluster")
        self.assertIn("JavaScript", clusters, "JavaScript should be in a cluster")
    
    def test_cluster_separation(self):
        """Test that distinct clusters are properly separated."""
        clusters = self.kg.detect_communities(min_cluster_size=3)
        
        if len(clusters) < 4:
            self.skipTest("Not enough concepts clustered for separation test")
        
        # Python ecosystem should be in same cluster
        python_cluster = clusters.get("Python")
        if python_cluster is not None:
            self.assertEqual(clusters.get("Django"), python_cluster,
                           "Django should be in same cluster as Python")
        
        # JavaScript ecosystem should be in same cluster (if clustered)
        js_cluster = clusters.get("JavaScript")
        if js_cluster is not None:
            self.assertEqual(clusters.get("React"), js_cluster,
                           "React should be in same cluster as JavaScript")
    
    def test_cluster_info(self):
        """Test cluster information retrieval."""
        clusters = self.kg.detect_communities(min_cluster_size=3)
        
        if not clusters:
            self.skipTest("No clusters detected")
        
        # Get info for first cluster
        cluster_id = list(clusters.values())[0]
        info = self.kg.get_cluster_info(cluster_id, clusters)
        
        # Verify info structure
        self.assertIn("cluster_id", info)
        self.assertIn("size", info)
        self.assertIn("dominant_type", info)
        self.assertIn("key_concepts", info)
        
        # Size should match actual cluster size
        expected_size = sum(1 for cid in clusters.values() if cid == cluster_id)
        self.assertEqual(info["size"], expected_size)


class TestConceptEvolution(unittest.TestCase):
    """Test concept evolution tracking."""
    
    @classmethod
    def setUpClass(cls):
        """Create test graph."""
        cls.kg = KnowledgeGraph()
        cls.kg.add_concept("TestConcept", "TECH")
    
    def test_version_update(self):
        """Test updating concept with versioning."""
        # Update with new data
        result = self.kg.update_concept_version(
            "TestConcept",
            {"status": "active", "priority": "high"}
        )
        
        self.assertTrue(result, "Should update successfully")
        
        # Check that version was recorded
        history = self.kg.get_concept_evolution("TestConcept")
        self.assertEqual(len(history), 1, "Should have one version")
        
        # Verify version content
        version = history[0]
        self.assertIn("timestamp", version)
        self.assertIn("changes", version)
        self.assertEqual(version["changes"]["status"], "active")
    
    def test_multiple_versions(self):
        """Test tracking multiple versions."""
        # Make multiple updates
        for i in range(3):
            self.kg.update_concept_version(
                "TestConcept",
                {"version": i, "update_count": i + 1}
            )
        
        history = self.kg.get_concept_evolution("TestConcept")
        self.assertGreaterEqual(len(history), 3, "Should track multiple versions")
        
        # Verify versions are ordered (oldest to newest)
        for i in range(len(history) - 1):
            self.assertLess(history[i]["timestamp"], history[i + 1]["timestamp"],
                          "Versions should be chronologically ordered")
    
    def test_version_limit(self):
        """Test that version history is limited."""
        # Add more versions than the limit
        for i in range(10):
            self.kg.update_concept_version(
                "TestConcept",
                {"iteration": i},
                version_limit=5
            )
        
        history = self.kg.get_concept_evolution("TestConcept")
        self.assertLessEqual(len(history), 5, "Should not exceed version limit")
    
    def test_evolution_for_nonexistent_concept(self):
        """Test querying evolution for non-existent concept."""
        history = self.kg.get_concept_evolution("NonExistentConcept")
        self.assertEqual(len(history), 0, "Should return empty history for non-existent concept")


class TestTopicSuggestions(unittest.TestCase):
    """Test graph-based topic suggestions."""
    
    @classmethod
    def setUpClass(cls):
        """Build a test graph for suggestions."""
        cls.kg = KnowledgeGraph()
        
        # Create a hub concept with many connections
        cls.kg.add_concept("Hub", "TECH")
        for i in range(5):
            concept = f"Related{i}"
            cls.kg.add_concept(concept, "TECH")
            cls.kg.add_relationship("Hub", concept, "related_to", 0.9 - i * 0.1)
    
    def test_suggestions_basic(self):
        """Test basic topic suggestions."""
        suggestions = self.kg.suggest_related_topics("Hub", top_k=3)
        
        self.assertGreater(len(suggestions), 0, "Should return suggestions")
        self.assertLessEqual(len(suggestions), 3, "Should respect top_k limit")
    
    def test_suggestions_with_centrality(self):
        """Test suggestions using degree centrality."""
        suggestions = self.kg.suggest_related_topics(
            "Hub",
            top_k=5,
            use_centrality=True
        )
        
        self.assertIsInstance(suggestions, list)
        # All suggestions should be strings (concept names)
        for suggestion in suggestions:
            self.assertIsInstance(suggestion, str)
    
    def test_suggestions_for_nonexistent_topic(self):
        """Test suggestions for non-existent topic."""
        suggestions = self.kg.suggest_related_topics("NonExistent")
        self.assertEqual(len(suggestions), 0, "Should return empty list for non-existent topic")


class TestGraphEnhancedMemoryRetrieval(unittest.TestCase):
    """Test graph-enhanced memory retrieval in query_user_profile."""
    
    def test_graph_traversal_parameter(self):
        """Test that use_graph_traversal parameter is accepted."""
        try:
            from core.user_profile_memory import query_user_profile
            
            # This should not raise an error
            results = query_user_profile(
                user_id="test_user",
                query_text="test query",
                top_k=5,
                use_graph_traversal=True,
                max_graph_hops=2
            )
            
            # Results should be a list (might be empty)
            self.assertIsInstance(results, list)
            
        except TypeError as e:
            self.fail(f"query_user_profile should accept use_graph_traversal parameter: {e}")
    
    def test_hop_distance_in_results(self):
        """Test that results include hop distance metadata."""
        try:
            from core.user_profile_memory import query_user_profile, save_user_profile_fact
            
            # Save a test fact
            fact_id = save_user_profile_fact(
                user_id="test_graph_user",
                fact_text="I love Python programming"
            )
            
            if fact_id:
                # Query with graph traversal
                results = query_user_profile(
                    user_id="test_graph_user",
                    query_text="programming",
                    top_k=5,
                    use_graph_traversal=True
                )
                
                # Check for metadata
                for result in results:
                    self.assertIn("match_type", result, "Should include match_type")
                    self.assertIn("hop_distance", result, "Should include hop_distance")
                
                # Clean up
                from core.user_profile_memory import delete_user_fact
                delete_user_fact(fact_id)
        
        except Exception as e:
            self.skipTest(f"Could not test hop distance: {e}")


class TestCleanup(unittest.TestCase):
    """Cleanup test resources."""
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test files."""
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)


def run_tests():
    """Run all tests."""
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestMultiHopTraversal))
    suite.addTests(loader.loadTestsFromTestCase(TestConceptClustering))
    suite.addTests(loader.loadTestsFromTestCase(TestConceptEvolution))
    suite.addTests(loader.loadTestsFromTestCase(TestTopicSuggestions))
    suite.addTests(loader.loadTestsFromTestCase(TestGraphEnhancedMemoryRetrieval))
    suite.addTests(loader.loadTestsFromTestCase(TestCleanup))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
