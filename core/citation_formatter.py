#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/citation_formatter.py — Inline Citation Formatting (Claude-style)

Implements Claude-like citation system:
- Inline citations with source numbers [1], [2]
- Automatic source attribution
- Citation deduplication
- Multiple formats (inline, footnote, bibliography)

Author: QuantumDev Enhancement
Version: 1.0.0
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse

log = logging.getLogger(__name__)


@dataclass
class Source:
    """A source for citations."""
    url: str
    title: str
    snippet: str = ""
    domain: str = ""
    citation_id: int = 0
    
    def __post_init__(self):
        if not self.domain and self.url:
            try:
                parsed = urlparse(self.url)
                self.domain = parsed.netloc.replace('www.', '')
            except Exception:
                self.domain = ""


@dataclass
class CitedResponse:
    """Response with embedded citations."""
    text: str
    sources: List[Source]
    footnotes: str = ""
    bibliography: str = ""
    citation_count: int = 0


class CitationFormatter:
    """
    Formats responses with inline citations like Claude.
    
    Features:
    - Assigns unique citation IDs to sources
    - Inserts inline citations [1], [2] in text
    - Generates footnotes and bibliography
    - Deduplicates sources by URL
    """
    
    # Phrases that indicate a claim needing citation
    CLAIM_PATTERNS = [
        r'secondo\s+[^,\.]+',  # "secondo X"
        r'studi\s+(?:mostrano|dimostrano|indicano)',
        r'(?:ricerche|dati|statistiche)\s+(?:mostrano|indicano|confermano)',
        r'\d+(?:[,.]\d+)?%',  # Percentages
        r'(?:nel|dal|fino al)\s+\d{4}',  # Years
        r'(?:milioni|miliardi)\s+di',  # Large numbers
        r'esperti\s+(?:dicono|affermano|sostengono)',
        r'fonti\s+(?:riportano|confermano)',
    ]
    
    def __init__(self):
        """Initialize citation formatter."""
        self._source_cache: Dict[str, Source] = {}
    
    def deduplicate_sources(self, sources: List[Dict[str, Any]]) -> List[Source]:
        """
        Deduplicate sources by URL and assign citation IDs.
        
        Args:
            sources: List of source dicts with url, title, snippet
            
        Returns:
            List of unique Source objects with citation IDs
        """
        seen_urls: set = set()
        unique_sources: List[Source] = []
        citation_id = 1
        
        for source_dict in sources:
            url = source_dict.get('url', '').strip()
            if not url or url in seen_urls:
                continue
            
            seen_urls.add(url)
            source = Source(
                url=url,
                title=source_dict.get('title', ''),
                snippet=source_dict.get('snippet', ''),
                citation_id=citation_id
            )
            unique_sources.append(source)
            citation_id += 1
        
        return unique_sources
    
    def find_citation_points(self, text: str) -> List[Tuple[int, int]]:
        """
        Find positions in text where citations should be inserted.
        
        Args:
            text: Response text
            
        Returns:
            List of (start, end) positions for citation points
        """
        points = []
        
        for pattern in self.CLAIM_PATTERNS:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                points.append((match.start(), match.end()))
        
        # Also find sentence ends that might need citations
        # (after factual statements before period)
        sentence_pattern = r'[A-Z][^.!?]*[.!?]'
        for match in re.finditer(sentence_pattern, text):
            sentence = match.group()
            # Check if sentence contains data-like content
            if re.search(r'\d+|(?:secondo|studi|dati|statistiche)', sentence, re.IGNORECASE):
                points.append((match.start(), match.end() - 1))  # Before the period
        
        return points
    
    def insert_inline_citations(
        self,
        text: str,
        sources: List[Source],
        max_citations_per_sentence: int = 2
    ) -> str:
        """
        Insert inline citations in text.
        
        Uses heuristics to determine where citations should be placed,
        matching content to relevant sources.
        
        Args:
            text: Original response text
            sources: List of sources with citation IDs
            max_citations_per_sentence: Max citations per sentence
            
        Returns:
            Text with inline citations [1], [2], etc.
        """
        if not sources or not text:
            return text
        
        # Build keyword index for sources
        source_keywords: Dict[int, set] = {}
        for source in sources:
            keywords = set()
            # Extract keywords from title and snippet
            for text_field in [source.title, source.snippet]:
                if text_field:
                    words = re.findall(r'\b\w{4,}\b', text_field.lower())
                    keywords.update(words)
            source_keywords[source.citation_id] = keywords
        
        # Process sentence by sentence
        sentences = re.split(r'(?<=[.!?])\s+', text)
        cited_sentences = []
        
        for sentence in sentences:
            if not sentence.strip():
                continue
            
            # Find matching sources for this sentence
            sentence_lower = sentence.lower()
            sentence_words = set(re.findall(r'\b\w{4,}\b', sentence_lower))
            
            matches: List[Tuple[int, int]] = []  # (citation_id, match_count)
            for cid, keywords in source_keywords.items():
                overlap = len(sentence_words & keywords)
                if overlap >= 2:  # At least 2 matching keywords
                    matches.append((cid, overlap))
            
            # Sort by match count and take top N
            matches.sort(key=lambda x: x[1], reverse=True)
            best_matches = [cid for cid, _ in matches[:max_citations_per_sentence]]
            
            # Insert citations before final punctuation
            if best_matches:
                citation_str = ''.join([f'[{cid}]' for cid in best_matches])
                
                # Find position to insert (before final punctuation)
                match = re.search(r'([.!?])\s*$', sentence)
                if match:
                    insert_pos = match.start()
                    sentence = sentence[:insert_pos] + ' ' + citation_str + sentence[insert_pos:]
                else:
                    sentence = sentence + ' ' + citation_str
            
            cited_sentences.append(sentence)
        
        return ' '.join(cited_sentences)
    
    def generate_footnotes(self, sources: List[Source]) -> str:
        """
        Generate footnotes for sources.
        
        Args:
            sources: List of sources with citation IDs
            
        Returns:
            Formatted footnotes string
        """
        if not sources:
            return ""
        
        lines = ["\n---\n**Fonti:**"]
        for source in sources:
            domain = source.domain or "fonte"
            line = f"[{source.citation_id}] {source.title} ({domain})"
            lines.append(line)
        
        return '\n'.join(lines)
    
    def generate_bibliography(self, sources: List[Source]) -> str:
        """
        Generate full bibliography with URLs.
        
        Args:
            sources: List of sources
            
        Returns:
            Formatted bibliography string
        """
        if not sources:
            return ""
        
        lines = ["\n---\n**Bibliografia completa:**\n"]
        for source in sources:
            lines.append(f"[{source.citation_id}] **{source.title}**")
            lines.append(f"    URL: {source.url}")
            if source.snippet:
                # Show first 150 chars of snippet
                snippet_preview = source.snippet[:150]
                if len(source.snippet) > 150:
                    snippet_preview += "..."
                lines.append(f"    > {snippet_preview}")
            lines.append("")
        
        return '\n'.join(lines)
    
    def format_response(
        self,
        text: str,
        sources: List[Dict[str, Any]],
        style: str = "inline",
        include_bibliography: bool = True
    ) -> CitedResponse:
        """
        Format a response with citations.
        
        Args:
            text: Original response text
            sources: List of source dicts
            style: Citation style ("inline", "footnote", "minimal")
            include_bibliography: Include full bibliography
            
        Returns:
            CitedResponse with formatted text and sources
        """
        # Deduplicate sources
        unique_sources = self.deduplicate_sources(sources)
        
        if not unique_sources:
            return CitedResponse(
                text=text,
                sources=[],
                citation_count=0
            )
        
        # Insert inline citations
        if style in ["inline", "footnote"]:
            cited_text = self.insert_inline_citations(text, unique_sources)
        else:
            cited_text = text
        
        # Count citations in text
        citation_count = len(re.findall(r'\[\d+\]', cited_text))
        
        # Generate footnotes
        footnotes = ""
        if style in ["inline", "footnote"]:
            footnotes = self.generate_footnotes(unique_sources)
        
        # Generate bibliography
        bibliography = ""
        if include_bibliography and style != "minimal":
            bibliography = self.generate_bibliography(unique_sources)
        
        return CitedResponse(
            text=cited_text + footnotes,
            sources=unique_sources,
            footnotes=footnotes,
            bibliography=bibliography,
            citation_count=citation_count
        )
    
    def format_for_telegram(
        self,
        text: str,
        sources: List[Dict[str, Any]],
        max_sources: int = 3
    ) -> str:
        """
        Format response for Telegram with compact citations.
        
        Args:
            text: Original response text
            sources: List of source dicts
            max_sources: Maximum number of sources to show
            
        Returns:
            Telegram-formatted string
        """
        unique_sources = self.deduplicate_sources(sources)[:max_sources]
        
        if not unique_sources:
            return text
        
        # Add sources at the end in a compact format
        source_lines = ["\n\n📚 *Fonti:*"]
        for source in unique_sources:
            # Telegram markdown link: [text](url)
            title = source.title[:50] + "..." if len(source.title) > 50 else source.title
            source_lines.append(f"• [{title}]({source.url})")
        
        return text + '\n'.join(source_lines)
    
    def format_for_api(
        self,
        text: str,
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Format response for API with structured data.
        
        Args:
            text: Original response text
            sources: List of source dicts
            
        Returns:
            Dict with text, sources, and citation metadata
        """
        result = self.format_response(text, sources, style="inline")
        
        return {
            "text": result.text,
            "sources": [
                {
                    "id": s.citation_id,
                    "url": s.url,
                    "title": s.title,
                    "domain": s.domain,
                }
                for s in result.sources
            ],
            "citation_count": result.citation_count,
            "has_citations": result.citation_count > 0,
        }


# === Singleton Instance ===
_formatter_instance: Optional[CitationFormatter] = None


def get_citation_formatter() -> CitationFormatter:
    """
    Get or create CitationFormatter singleton.
    
    Returns:
        CitationFormatter instance
    """
    global _formatter_instance
    
    if _formatter_instance is None:
        _formatter_instance = CitationFormatter()
    
    return _formatter_instance


def format_with_citations(
    text: str,
    sources: List[Dict[str, Any]],
    style: str = "inline"
) -> str:
    """
    Utility function to format text with citations.
    
    Args:
        text: Response text
        sources: List of source dicts
        style: Citation style
        
    Returns:
        Formatted text with citations
    """
    formatter = get_citation_formatter()
    result = formatter.format_response(text, sources, style=style)
    return result.text
