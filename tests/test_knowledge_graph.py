#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_knowledge_graph.py — Tests for Knowledge Graph Layer

Tests for:
- Concept extraction
- Knowledge graph construction
- Relationship inference
- Graph queries and context retrieval
"""

import sys
import os
import unittest
import tempfile
from typing import List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Set test environment variables before importing modules
os.environ["ENABLE_KNOWLEDGE_GRAPH"] = "1"
os.environ["KG_SIMILARITY_THRESHOLD"] = "0.6"
os.environ["SPACY_MODEL"] = "en_core_web_sm"

# Create temp directory for test graph
test_dir = tempfile.mkdtemp()
os.environ["KG_PERSIST_PATH"] = os.path.join(test_dir, "test_graph.graphml")

from core.concept_extractor import (
    extract_concepts,
    extract_relationships,
    _is_valid_concept,
    _normalize_concept,
)
from core.knowledge_graph import (
    KnowledgeGraph,
    get_knowledge_graph,
)


class TestConceptExtractor(unittest.TestCase):
    """Test cases for concept extraction."""
    
    def test_is_valid_concept(self):
        """Test concept validation."""
        # Valid concepts
        self.assertTrue(_is_valid_concept("Python"))
        self.assertTrue(_is_valid_concept("FastAPI"))
        self.assertTrue(_is_valid_concept("Machine Learning"))
        
        # Invalid concepts
        self.assertFalse(_is_valid_concept(""))
        self.assertFalse(_is_valid_concept("a"))  # Too short
        self.assertFalse(_is_valid_concept("x" * 200))  # Too long
        self.assertFalse(_is_valid_concept("123"))  # No letters
        self.assertFalse(_is_valid_concept("something"))  # Noise term
    
    def test_normalize_concept(self):
        """Test concept normalization."""
        self.assertEqual(_normalize_concept("  python  "), "Python")
        self.assertEqual(_normalize_concept("FASTAPI"), "Fastapi")
        self.assertEqual(_normalize_concept("machine   learning"), "Machine Learning")
    
    def test_extract_concepts_basic(self):
        """Test basic concept extraction."""
        text = "I'm working on a Python project using FastAPI and ChromaDB."
        concepts = extract_concepts(text)
        
        self.assertGreater(len(concepts), 0, "Should extract at least one concept")
        
        # Check if we extracted tech terms
        concept_texts = [c.text.lower() for c in concepts]
        has_tech = any(term in concept_texts for term in ["python", "fastapi", "chromadb"])
        self.assertTrue(has_tech, "Should extract technology terms")
    
    def test_extract_concepts_with_entities(self):
        """Test concept extraction with named entities."""
        text = "Matteo lives in Rome and works with developers in Milan."
        concepts = extract_concepts(text)
        
        self.assertGreater(len(concepts), 0)
        
        # Check for person or place extraction
        concept_types = [c.type for c in concepts]
        has_entities = any(t in concept_types for t in ["PERSON", "PLACE", "ENTITY"])
        self.assertTrue(has_entities, "Should extract named entities")
    
    def test_extract_relationships(self):
        """Test explicit relationship extraction."""
        text = "Python uses NumPy. FastAPI depends on Pydantic."
        relationships = extract_relationships(text)
        
        self.assertGreater(len(relationships), 0, "Should extract relationships")
        
        # Check relationship structure
        for rel in relationships:
            self.assertIn("source", rel)
            self.assertIn("target", rel)
            self.assertIn("relation", rel)


class TestKnowledgeGraph(unittest.TestCase):
    """Test cases for knowledge graph functionality."""
    
    @classmethod
    def setUpClass(cls):
        """Set up test knowledge graph."""
        cls.kg = KnowledgeGraph()
    
    @classmethod
    def tearDownClass(cls):
        """Clean up test graph file."""
        import shutil
        if os.path.exists(test_dir):
            shutil.rmtree(test_dir)
    
    def test_add_concept(self):
        """Test adding concepts to graph."""
        result = self.kg.add_concept("TestConcept", "TECH")
        self.assertTrue(result, "Should add concept successfully")
        self.assertTrue(self.kg.graph.has_node("TestConcept"))
        
        # Check metadata
        node_data = self.kg.graph.nodes["TestConcept"]
        self.assertEqual(node_data["type"], "TECH")
        self.assertIn("created_at", node_data)
    
    def test_add_duplicate_concept(self):
        """Test adding duplicate concept."""
        self.kg.add_concept("DuplicateTest", "TECH")
        result = self.kg.add_concept("DuplicateTest", "TECH")
        self.assertTrue(result, "Should handle duplicate gracefully")
    
    def test_add_relationship(self):
        """Test adding relationships."""
        self.kg.add_concept("SourceNode", "TECH")
        self.kg.add_concept("TargetNode", "TECH")
        
        result = self.kg.add_relationship("SourceNode", "TargetNode", "uses", 0.8)
        self.assertTrue(result, "Should add relationship")
        self.assertTrue(self.kg.graph.has_edge("SourceNode", "TargetNode"))
        
        # Check edge data
        edge_data = self.kg.graph.edges["SourceNode", "TargetNode"]
        self.assertEqual(edge_data["relation"], "uses")
        self.assertEqual(edge_data["weight"], 0.8)
    
    def test_find_related(self):
        """Test finding related concepts."""
        # Build a small graph
        self.kg.add_concept("CenterNode", "TECH")
        self.kg.add_concept("Related1", "TECH")
        self.kg.add_concept("Related2", "TECH")
        
        self.kg.add_relationship("CenterNode", "Related1", "uses", 0.9)
        self.kg.add_relationship("CenterNode", "Related2", "depends_on", 0.8)
        
        # Find related
        related = self.kg.find_related("CenterNode", depth=1)
        
        self.assertGreater(len(related), 0, "Should find related concepts")
        related_names = [r.concept for r in related]
        self.assertIn("Related1", related_names)
        self.assertIn("Related2", related_names)
    
    def test_get_context(self):
        """Test getting context for a concept."""
        self.kg.add_concept("ContextTest", "TECH")
        self.kg.add_concept("ContextRelated", "TECH")
        self.kg.add_relationship("ContextTest", "ContextRelated", "related_to", 0.75)
        
        context = self.kg.get_context("ContextTest")
        
        self.assertIsInstance(context, str)
        self.assertIn("ContextTest", context)
        self.assertIn("TECH", context)
    
    def test_visualize_subgraph(self):
        """Test ASCII visualization."""
        self.kg.add_concept("VisualCenter", "TECH")
        self.kg.add_concept("VisualRelated", "TECH")
        self.kg.add_relationship("VisualCenter", "VisualRelated", "uses", 0.9)
        
        visualization = self.kg.visualize_subgraph("VisualCenter", depth=1)
        
        self.assertIsInstance(visualization, str)
        self.assertIn("VisualCenter", visualization)
    
    def test_get_stats(self):
        """Test graph statistics."""
        stats = self.kg.get_stats()
        
        self.assertIn("nodes", stats)
        self.assertIn("edges", stats)
        self.assertIn("node_types", stats)
        self.assertIn("avg_degree", stats)
        
        self.assertIsInstance(stats["nodes"], int)
        self.assertIsInstance(stats["edges"], int)
    
    def test_save_and_load_graph(self):
        """Test graph persistence."""
        # Add some data
        self.kg.add_concept("PersistTest", "TECH")
        
        # Save
        result = self.kg.save_graph()
        self.assertTrue(result, "Should save successfully")
        self.assertTrue(os.path.exists(os.environ["KG_PERSIST_PATH"]))
        
        # Create new instance (should load saved graph)
        new_kg = KnowledgeGraph()
        self.assertTrue(new_kg.graph.has_node("PersistTest"), "Should load saved graph")
    
    def test_cleanup_old_concepts(self):
        """Test cleaning up old isolated concepts."""
        # Add an isolated concept with old timestamp
        self.kg.add_concept("OldIsolated", "TECH", metadata={"created_at": 0})
        
        # Run cleanup
        removed = self.kg.cleanup_old_concepts(days=1)
        
        self.assertIsInstance(removed, int)
        # Old isolated concept should be removed
        self.assertFalse(self.kg.graph.has_node("OldIsolated"))


class TestKnowledgeGraphIntegration(unittest.TestCase):
    """Test integration with concept extraction."""
    
    def test_extract_and_add_concepts(self):
        """Test extracting concepts and adding to graph."""
        kg = get_knowledge_graph()
        if kg is None:
            self.skipTest("Knowledge graph not available")
        
        text = "I'm building a web application with Python and FastAPI."
        concepts = extract_concepts(text)
        
        # Add concepts to graph
        for concept in concepts[:5]:
            kg.add_concept(concept.text, concept.type)
        
        # Verify they were added
        stats = kg.get_stats()
        self.assertGreater(stats["nodes"], 0)
    
    def test_extract_and_add_relationships(self):
        """Test extracting and adding relationships."""
        kg = get_knowledge_graph()
        if kg is None:
            self.skipTest("Knowledge graph not available")
        
        text = "FastAPI depends on Pydantic. Pydantic uses type hints."
        relationships = extract_relationships(text)
        
        # Add relationships to graph
        for rel in relationships:
            kg.add_relationship(rel["source"], rel["target"], rel["relation"], 0.85)
        
        # Verify relationships exist
        stats = kg.get_stats()
        self.assertGreater(stats["edges"], 0)


def run_tests():
    """Run all tests."""
    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    
    # Add test classes
    suite.addTests(loader.loadTestsFromTestCase(TestConceptExtractor))
    suite.addTests(loader.loadTestsFromTestCase(TestKnowledgeGraph))
    suite.addTests(loader.loadTestsFromTestCase(TestKnowledgeGraphIntegration))
    
    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    
    return result.wasSuccessful()


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
