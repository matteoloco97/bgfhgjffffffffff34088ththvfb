#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/unit/test_parallel_synthesis.py - Unit tests for parallel synthesis engine.

Tests parallel LLM calls, retry logic, timeout handling, and synthesis merging.
"""

import os
import sys
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# IMPORT TESTS
# ============================================================================

class TestParallelSynthesisImports:
    """Tests for parallel synthesis module imports."""
    
    def test_import_parallel_synthesis_module(self):
        """Test that parallel synthesis module can be imported."""
        from core.parallel_synthesis import (
            parallel_synthesize_documents,
            is_parallel_synthesis_enabled,
            get_parallel_synthesis_config,
        )
        
        assert callable(parallel_synthesize_documents)
        assert callable(is_parallel_synthesis_enabled)
        assert callable(get_parallel_synthesis_config)
    
    def test_import_internal_functions(self):
        """Test internal helper functions can be imported."""
        from core.parallel_synthesis import (
            _synthesize_single_document,
            _merge_syntheses,
        )
        
        assert callable(_synthesize_single_document)
        assert callable(_merge_syntheses)


# ============================================================================
# CONFIGURATION TESTS
# ============================================================================

class TestParallelSynthesisConfig:
    """Tests for parallel synthesis configuration."""
    
    def test_get_parallel_synthesis_config(self):
        """Test getting parallel synthesis configuration."""
        from core.parallel_synthesis import get_parallel_synthesis_config
        
        config = get_parallel_synthesis_config()
        
        assert isinstance(config, dict)
        assert 'enabled' in config
        assert 'max_concurrent' in config
        assert 'timeout' in config
        assert 'token_limit' in config
        assert 'retry_attempts' in config
    
    def test_config_defaults(self):
        """Test configuration default values."""
        from core.parallel_synthesis import get_parallel_synthesis_config
        
        config = get_parallel_synthesis_config()
        
        assert config['max_concurrent'] >= 1
        assert config['timeout'] > 0
        assert config['token_limit'] > 0
        assert config['retry_attempts'] >= 0
    
    def test_is_parallel_synthesis_enabled(self):
        """Test parallel synthesis enabled check."""
        from core.parallel_synthesis import is_parallel_synthesis_enabled
        
        result = is_parallel_synthesis_enabled()
        
        assert isinstance(result, bool)
    
    def test_env_int_helper(self):
        """Test environment integer parsing helper."""
        from core.parallel_synthesis import _env_int
        
        # Test with valid value
        os.environ['TEST_INT'] = '42'
        assert _env_int('TEST_INT', 0) == 42
        
        # Test with invalid value
        os.environ['TEST_INT'] = 'invalid'
        assert _env_int('TEST_INT', 10) == 10
        
        # Cleanup
        del os.environ['TEST_INT']
    
    def test_env_float_helper(self):
        """Test environment float parsing helper."""
        from core.parallel_synthesis import _env_float
        
        # Test with valid value
        os.environ['TEST_FLOAT'] = '3.14'
        assert _env_float('TEST_FLOAT', 0.0) == 3.14
        
        # Test with invalid value
        os.environ['TEST_FLOAT'] = 'invalid'
        assert _env_float('TEST_FLOAT', 1.0) == 1.0
        
        # Cleanup
        del os.environ['TEST_FLOAT']
    
    def test_env_bool_helper(self):
        """Test environment boolean parsing helper."""
        from core.parallel_synthesis import _env_bool
        
        # Test true values
        for val in ['1', 'true', 'yes', 'on']:
            os.environ['TEST_BOOL'] = val
            assert _env_bool('TEST_BOOL', False) is True
        
        # Test false values
        for val in ['0', 'false', 'no', 'off']:
            os.environ['TEST_BOOL'] = val
            assert _env_bool('TEST_BOOL', True) is False
        
        # Cleanup
        if 'TEST_BOOL' in os.environ:
            del os.environ['TEST_BOOL']


# ============================================================================
# SYNTHESIS MERGING TESTS
# ============================================================================

class TestSynthesisMerging:
    """Tests for synthesis merging functionality."""
    
    def test_merge_syntheses_empty_list(self):
        """Test merging empty list of syntheses."""
        from core.parallel_synthesis import _merge_syntheses
        
        result = _merge_syntheses([])
        
        assert result == ""
    
    def test_merge_syntheses_single_item(self):
        """Test merging single synthesis."""
        from core.parallel_synthesis import _merge_syntheses
        
        syntheses = ["This is a single synthesis."]
        result = _merge_syntheses(syntheses)
        
        assert result == "This is a single synthesis."
    
    def test_merge_syntheses_multiple_items(self):
        """Test merging multiple syntheses."""
        from core.parallel_synthesis import _merge_syntheses
        
        syntheses = [
            "First synthesis content.",
            "Second synthesis content.",
            "Third synthesis content."
        ]
        result = _merge_syntheses(syntheses)
        
        assert "First synthesis content." in result
        assert "Second synthesis content." in result
        assert "Third synthesis content." in result
    
    def test_merge_syntheses_with_formatting(self):
        """Test merging preserves formatting."""
        from core.parallel_synthesis import _merge_syntheses
        
        syntheses = [
            "**TL;DR:** Summary 1\n\n• Point 1",
            "**TL;DR:** Summary 2\n\n• Point 2"
        ]
        result = _merge_syntheses(syntheses)
        
        assert "**TL;DR:**" in result
        assert "• Point 1" in result
        assert "• Point 2" in result


# ============================================================================
# PARALLEL SYNTHESIS FUNCTION TESTS
# ============================================================================

class TestParallelSynthesizeDocuments:
    """Tests for parallel_synthesize_documents function."""
    
    @pytest.mark.asyncio
    async def test_empty_documents_list(self):
        """Test synthesis with empty documents list."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        synthesis, stats = await parallel_synthesize_documents(
            query="test query",
            documents=[],
        )
        
        assert synthesis == ""
        assert stats['total_documents'] == 0
        assert stats['successful'] == 0
        assert stats['failed'] == 0
        assert stats['success_rate'] == 0.0
    
    @pytest.mark.asyncio
    async def test_stats_structure(self):
        """Test that stats have expected structure."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        synthesis, stats = await parallel_synthesize_documents(
            query="test query",
            documents=[],
        )
        
        expected_keys = [
            'total_documents',
            'successful',
            'failed',
            'success_rate',
            'total_duration_ms',
            'speedup'
        ]
        
        for key in expected_keys:
            assert key in stats, f"Missing key: {key}"
    
    @pytest.mark.asyncio
    async def test_respects_max_concurrent(self):
        """Test that max_concurrent is respected."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        documents = [
            {"idx": i, "title": f"Doc {i}", "url": f"http://example.com/{i}", "text": f"Content {i}"}
            for i in range(10)
        ]
        
        # Mock the LLM at the import location in the module
        with patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Synthesized content"
            
            synthesis, stats = await parallel_synthesize_documents(
                query="test query",
                documents=documents,
                max_concurrent=3,
                timeout=1.0,
            )
            
            # Should only process max_concurrent documents
            assert stats['total_documents'] <= 3
    
    @pytest.mark.asyncio
    async def test_handles_llm_timeout(self):
        """Test handling of LLM timeout."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        documents = [
            {"idx": 1, "title": "Doc 1", "url": "http://example.com/1", "text": "Content 1"}
        ]
        
        # Test with very short timeout - should handle gracefully
        synthesis, stats = await parallel_synthesize_documents(
            query="test query",
            documents=documents,
            max_concurrent=1,
            timeout=0.001,  # Very short timeout
            retry_attempts=0,
        )
        
        # Should handle gracefully
        assert isinstance(stats, dict)
        assert 'total_documents' in stats
    
    @pytest.mark.asyncio
    async def test_success_rate_calculation(self):
        """Test success rate calculation."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        # Test with empty docs - 0% success rate
        synthesis, stats = await parallel_synthesize_documents(
            query="test query",
            documents=[],
        )
        
        # Success rate should be 0 for empty
        assert stats['success_rate'] == 0.0


# ============================================================================
# SINGLE DOCUMENT SYNTHESIS TESTS
# ============================================================================

class TestSynthesizeSingleDocument:
    """Tests for _synthesize_single_document function."""
    
    @pytest.mark.asyncio
    async def test_successful_synthesis(self):
        """Test successful document synthesis."""
        from core.parallel_synthesis import _synthesize_single_document
        
        document = {
            "idx": 1,
            "title": "Test Document",
            "url": "http://example.com/test",
            "text": "This is test content for synthesis."
        }
        
        with patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "This is the synthesized result that is long enough."
            
            with patch('backend.synthesis_prompt_v2.build_aggressive_synthesis_prompt', return_value="prompt"):
                result, stats = await _synthesize_single_document(
                    query="test query",
                    document=document,
                    persona="",
                    token_limit=80,
                    timeout=5.0,
                    retry_attempts=2,
                )
                
                assert result is not None
                assert stats['success'] is True
                assert stats['idx'] == 1
    
    @pytest.mark.asyncio
    async def test_synthesis_with_empty_result(self):
        """Test synthesis that returns empty result."""
        from core.parallel_synthesis import _synthesize_single_document
        
        document = {
            "idx": 1,
            "title": "Test Document",
            "url": "http://example.com/test",
            "text": "Content"
        }
        
        with patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = ""  # Empty result
            
            with patch('backend.synthesis_prompt_v2.build_aggressive_synthesis_prompt', return_value="prompt"):
                result, stats = await _synthesize_single_document(
                    query="test query",
                    document=document,
                    persona="",
                    token_limit=80,
                    timeout=5.0,
                    retry_attempts=0,
                )
                
                assert result is None
                assert stats['success'] is False
    
    @pytest.mark.asyncio
    async def test_synthesis_stats_structure(self):
        """Test synthesis stats have expected structure."""
        from core.parallel_synthesis import _synthesize_single_document
        
        document = {
            "idx": 1,
            "title": "Test Document",
            "url": "http://example.com/test",
            "text": "Content"
        }
        
        with patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = "Synthesized content long enough"
            
            with patch('backend.synthesis_prompt_v2.build_aggressive_synthesis_prompt', return_value="prompt"):
                result, stats = await _synthesize_single_document(
                    query="test query",
                    document=document,
                    persona="",
                    token_limit=80,
                    timeout=5.0,
                    retry_attempts=0,
                )
                
                expected_keys = ['idx', 'title', 'attempts', 'success', 'error', 'duration_ms']
                for key in expected_keys:
                    assert key in stats, f"Missing key: {key}"


# ============================================================================
# RETRY LOGIC TESTS
# ============================================================================

class TestRetryLogic:
    """Tests for retry logic in synthesis."""
    
    @pytest.mark.asyncio
    async def test_retry_on_failure(self):
        """Test that synthesis retries on failure."""
        from core.parallel_synthesis import _synthesize_single_document
        
        document = {
            "idx": 1,
            "title": "Test Document",
            "url": "http://example.com/test",
            "text": "Content"
        }
        
        call_count = [0]
        
        async def failing_then_success(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] < 2:
                raise Exception("Temporary failure")
            return "Success after retry - this is long enough"
        
        with patch('core.chat_engine.reply_with_llm', side_effect=failing_then_success):
            with patch('backend.synthesis_prompt_v2.build_aggressive_synthesis_prompt', return_value="prompt"):
                result, stats = await _synthesize_single_document(
                    query="test query",
                    document=document,
                    persona="",
                    token_limit=80,
                    timeout=5.0,
                    retry_attempts=2,
                )
                
                assert stats['attempts'] >= 2
    
    @pytest.mark.asyncio
    async def test_max_retry_attempts_respected(self):
        """Test that max retry attempts are respected."""
        from core.parallel_synthesis import _synthesize_single_document
        
        document = {
            "idx": 1,
            "title": "Test Document",
            "url": "http://example.com/test",
            "text": "Content"
        }
        
        call_count = [0]
        
        async def always_failing(*args, **kwargs):
            call_count[0] += 1
            raise Exception("Always fails")
        
        with patch('core.chat_engine.reply_with_llm', side_effect=always_failing):
            with patch('backend.synthesis_prompt_v2.build_aggressive_synthesis_prompt', return_value="prompt"):
                result, stats = await _synthesize_single_document(
                    query="test query",
                    document=document,
                    persona="",
                    token_limit=80,
                    timeout=5.0,
                    retry_attempts=2,  # Max 2 retries = 3 total attempts
                )
                
                assert result is None
                assert stats['success'] is False
                # Should attempt initial + retries = 3 total
                assert stats['attempts'] <= 3


# ============================================================================
# EDGE CASES
# ============================================================================

class TestParallelSynthesisEdgeCases:
    """Tests for edge cases in parallel synthesis."""
    
    @pytest.mark.asyncio
    async def test_synthesis_with_special_characters(self):
        """Test synthesis with special characters in content."""
        from core.parallel_synthesis import _merge_syntheses
        
        syntheses = [
            "Special chars: <>&\"'",
            "Unicode: 日本語 中文 한국어",
            "Emoji: 🚀 🎉 💻"
        ]
        
        result = _merge_syntheses(syntheses)
        
        assert "日本語" in result
        assert "🚀" in result
    
    @pytest.mark.asyncio
    async def test_synthesis_with_very_long_document(self):
        """Test synthesis with very long document."""
        from core.parallel_synthesis import parallel_synthesize_documents
        
        documents = [
            {
                "idx": 1,
                "title": "Long Document",
                "url": "http://example.com/long",
                "text": "x" * 10000  # Very long content
            }
        ]
        
        synthesis, stats = await parallel_synthesize_documents(
            query="test query",
            documents=documents,
            max_concurrent=1,
            timeout=0.01,  # Very short timeout
            retry_attempts=0,
        )
        
        # Should handle gracefully (either succeed or fail cleanly)
        assert isinstance(synthesis, str)
        assert 'total_documents' in stats
    
    def test_config_with_missing_env_vars(self):
        """Test configuration with missing environment variables."""
        from core.parallel_synthesis import get_parallel_synthesis_config
        
        # Remove env vars if they exist
        env_vars_to_remove = [
            'PARALLEL_SYNTHESIS_ENABLED',
            'PARALLEL_SYNTHESIS_MAX_CONCURRENT',
            'PARALLEL_SYNTHESIS_TIMEOUT',
            'PARALLEL_SYNTHESIS_TOKEN_LIMIT',
            'PARALLEL_SYNTHESIS_RETRY_ATTEMPTS',
        ]
        
        original_values = {}
        for var in env_vars_to_remove:
            if var in os.environ:
                original_values[var] = os.environ.pop(var)
        
        try:
            # Should use defaults without error
            config = get_parallel_synthesis_config()
            
            assert isinstance(config['enabled'], bool)
            assert isinstance(config['max_concurrent'], int)
            assert isinstance(config['timeout'], float)
        finally:
            # Restore env vars
            os.environ.update(original_values)
