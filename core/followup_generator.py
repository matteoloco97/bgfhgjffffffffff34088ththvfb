#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/followup_generator.py — Smart Follow-up Question Generator

Implements Claude-like follow-up suggestions:
- Context-aware question generation
- Proactive exploration suggestions
- Topic deepening questions
- Related topic discovery

Author: QuantumDev Enhancement
Version: 1.0.0
"""

from __future__ import annotations

import os
import re
import logging
from typing import List, Dict, Any, Optional, Set
from dataclasses import dataclass

log = logging.getLogger(__name__)


# === Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


FOLLOWUP_ENABLED = _env_bool("FOLLOWUP_SUGGESTIONS_ENABLED", True)
MAX_FOLLOWUP_QUESTIONS = _env_int("MAX_FOLLOWUP_QUESTIONS", 3)


@dataclass
class FollowUpSuggestion:
    """A suggested follow-up question."""
    question: str
    category: str  # "deepening", "related", "practical", "comparison"
    relevance: float  # 0.0 - 1.0
    reason: str = ""


class FollowUpGenerator:
    """
    Generates intelligent follow-up question suggestions.
    
    Features:
    - Context-aware question generation
    - Multiple question categories
    - Relevance scoring
    - Deduplication
    """
    
    # Question templates by category
    TEMPLATES = {
        "deepening": [
            "Puoi approfondire {topic}?",
            "Quali sono i dettagli di {topic}?",
            "Come funziona esattamente {topic}?",
            "Perché {topic} è importante?",
            "Quali sono le implicazioni di {topic}?",
        ],
        "related": [
            "Qual è la relazione tra {topic} e {related}?",
            "Come si collega {topic} a {context}?",
            "Ci sono alternative a {topic}?",
            "Cosa è cambiato riguardo a {topic} negli ultimi anni?",
        ],
        "practical": [
            "Come posso applicare {topic} nella pratica?",
            "Quali sono i passaggi per {action}?",
            "Quali strumenti servono per {topic}?",
            "Qual è il modo migliore per iniziare con {topic}?",
        ],
        "comparison": [
            "Quali sono le differenze tra {topic} e {alternative}?",
            "Qual è meglio: {option1} o {option2}?",
            "Pro e contro di {topic}?",
            "Come si confronta {topic} con le alternative?",
        ],
        "current": [
            "Quali sono le ultime novità su {topic}?",
            "Qual è la situazione attuale di {topic}?",
            "Come sta evolvendo {topic}?",
        ],
    }
    
    # Entity extraction patterns
    ENTITY_PATTERNS = [
        r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b',  # Capitalized words/phrases
        r'\b([A-Z]{2,})\b',  # Acronyms
        r'\b(\d+(?:[.,]\d+)?%)\b',  # Percentages
        r'\b(€?\d+(?:[.,]\d+)?(?:\s*(?:euro|EUR|USD|\$|milioni|miliardi))?)\b',  # Money
    ]
    
    # Stop words for entity extraction (Italian + English)
    STOP_ENTITIES = {
        "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
        "the", "a", "an", "this", "that", "these", "those",
        "cosa", "come", "quando", "dove", "perché", "quale",
        "what", "how", "when", "where", "why", "which",
        "inoltre", "quindi", "tuttavia", "perciò",
    }
    
    def __init__(self, llm_func=None):
        """
        Initialize follow-up generator.
        
        Args:
            llm_func: Optional LLM function for advanced generation
        """
        self.llm_func = llm_func
    
    def _extract_entities(self, text: str) -> List[str]:
        """
        Extract key entities from text.
        
        Args:
            text: Input text
            
        Returns:
            List of extracted entities
        """
        entities: Set[str] = set()
        
        for pattern in self.ENTITY_PATTERNS:
            matches = re.findall(pattern, text)
            for match in matches:
                entity = match.strip()
                if (len(entity) > 2 and 
                    entity.lower() not in self.STOP_ENTITIES):
                    entities.add(entity)
        
        return list(entities)[:10]  # Limit to top 10
    
    def _extract_topics(self, text: str) -> List[str]:
        """
        Extract main topics from text.
        
        Args:
            text: Input text
            
        Returns:
            List of topics
        """
        topics = []
        
        # First, try to extract key nouns/concepts from the text
        # Look for common topic patterns in Italian
        topic_patterns = [
            r'\b(?:la|il|lo|un|una|gli|le|i)\s+(\w{4,})\b',  # Articles + nouns
            r'\bè\s+(?:un[ao]?\s+)?(\w{4,})\b',  # "è una X", "è X"
            r'\bregistro\s+(\w+)\b',  # "registro X"
            r'\bsistema\s+(?:di\s+)?(\w+)\b',  # "sistema di X"
            r'\bpermette\s+di\s+(\w+)\b',  # "permette di X"
        ]
        
        for pattern in topic_patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                topic = match.group(1)
                if len(topic) > 3 and topic.lower() not in self.STOP_ENTITIES:
                    topics.append(topic.capitalize())
        
        # Find capitalized sequences (proper nouns)
        caps_pattern = r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\b'
        for match in re.finditer(caps_pattern, text):
            topic = match.group(1)
            if len(topic) > 3 and topic.lower() not in self.STOP_ENTITIES:
                topics.append(topic)
        
        # Find quoted terms
        quoted_pattern = r'"([^"]+)"|\'([^\']+)\''
        for match in re.finditer(quoted_pattern, text):
            topic = match.group(1) or match.group(2)
            if topic and len(topic) > 3:
                topics.append(topic)
        
        # Also extract from query - look for "Cos'è X" pattern
        query_pattern = r"cos[''`]?\s*[èe]\s+(?:la|il|lo|un|una|gli|le|i)?\s*(\w{4,})"
        for match in re.finditer(query_pattern, text, re.IGNORECASE):
            topic = match.group(1)
            if topic.lower() not in self.STOP_ENTITIES:
                topics.insert(0, topic.capitalize())  # Priority
        
        # Deduplicate while preserving order
        seen = set()
        unique_topics = []
        for t in topics:
            if t.lower() not in seen:
                unique_topics.append(t)
                seen.add(t.lower())
        
        return unique_topics[:5]
    
    def _detect_query_type(self, query: str) -> str:
        """
        Detect the type of the original query.
        
        Args:
            query: Original query
            
        Returns:
            Query type string
        """
        query_lower = query.lower()
        
        if any(kw in query_lower for kw in ['cos\'è', 'cosa è', 'what is', 'definizione']):
            return 'definition'
        elif any(kw in query_lower for kw in ['come', 'how to', 'modo', 'way']):
            return 'howto'
        elif any(kw in query_lower for kw in ['perché', 'why', 'reason', 'motivo']):
            return 'reason'
        elif any(kw in query_lower for kw in ['differenza', 'difference', 'vs', 'versus', 'confronto']):
            return 'comparison'
        elif any(kw in query_lower for kw in ['prezzo', 'price', 'costo', 'cost', 'quanto']):
            return 'price'
        elif any(kw in query_lower for kw in ['notizie', 'news', 'ultime', 'latest']):
            return 'news'
        else:
            return 'general'
    
    def generate_template_based(
        self,
        query: str,
        response: str,
        max_questions: int = MAX_FOLLOWUP_QUESTIONS
    ) -> List[FollowUpSuggestion]:
        """
        Generate follow-up questions using templates.
        
        Args:
            query: Original query
            response: LLM response
            max_questions: Maximum number of suggestions
            
        Returns:
            List of FollowUpSuggestion
        """
        suggestions = []
        
        # Extract entities and topics
        topics = self._extract_topics(response)
        entities = self._extract_entities(response)
        query_type = self._detect_query_type(query)
        
        if not topics and not entities:
            # Fallback to query-based extraction
            topics = self._extract_topics(query)
            entities = self._extract_entities(query)
        
        main_topic = topics[0] if topics else (entities[0] if entities else "questo argomento")
        
        # Select appropriate templates based on query type
        if query_type == 'definition':
            # After definition, suggest practical and deepening
            categories = ["practical", "deepening", "related"]
        elif query_type == 'howto':
            # After how-to, suggest alternatives and related
            categories = ["comparison", "related", "deepening"]
        elif query_type == 'comparison':
            # After comparison, suggest practical and current
            categories = ["practical", "current", "deepening"]
        elif query_type in ['price', 'news']:
            # After factual queries, suggest current and related
            categories = ["current", "related", "deepening"]
        else:
            categories = ["deepening", "related", "practical"]
        
        # Generate questions from templates
        for category in categories:
            if len(suggestions) >= max_questions:
                break
            
            templates = self.TEMPLATES.get(category, [])
            if not templates:
                continue
            
            # Select best template
            template = templates[0]
            
            try:
                # Fill in template
                if "{topic}" in template:
                    question = template.format(topic=main_topic)
                elif "{related}" in template and len(topics) > 1:
                    question = template.format(topic=main_topic, related=topics[1])
                elif "{context}" in template:
                    question = template.format(topic=main_topic, context="il contesto attuale")
                elif "{action}" in template:
                    question = template.format(action=f"implementare {main_topic}")
                elif "{alternative}" in template and len(topics) > 1:
                    question = template.format(topic=main_topic, alternative=topics[1])
                elif "{option1}" in template and "{option2}" in template and len(topics) > 1:
                    question = template.format(option1=main_topic, option2=topics[1])
                else:
                    question = template.format(topic=main_topic)
                
                suggestions.append(FollowUpSuggestion(
                    question=question,
                    category=category,
                    relevance=0.8 - (len(suggestions) * 0.1),
                    reason=f"Basato su {category}"
                ))
            except Exception as e:
                log.debug(f"Template fill error: {e}")
                continue
        
        return suggestions[:max_questions]
    
    async def generate_with_llm(
        self,
        query: str,
        response: str,
        max_questions: int = MAX_FOLLOWUP_QUESTIONS
    ) -> List[FollowUpSuggestion]:
        """
        Generate follow-up questions using LLM.
        
        Args:
            query: Original query
            response: LLM response
            max_questions: Maximum suggestions
            
        Returns:
            List of FollowUpSuggestion
        """
        if not self.llm_func:
            return self.generate_template_based(query, response, max_questions)
        
        prompt = f"""Genera {max_questions} domande di approfondimento per questa conversazione.

DOMANDA ORIGINALE: {query}

RISPOSTA DATA: {response[:500]}...

REGOLE:
1. Le domande devono essere naturali e pertinenti
2. Devono aiutare l'utente ad approfondire l'argomento
3. Includi domande pratiche, comparative, e di approfondimento
4. Ogni domanda su una nuova riga

OUTPUT (solo domande, una per riga):"""

        try:
            result = await self.llm_func(prompt, "")
            
            # Parse questions
            suggestions = []
            for i, line in enumerate(result.strip().split('\n')):
                line = line.strip()
                # Remove numbering
                line = re.sub(r'^\d+[.)]\s*', '', line)
                
                # Accept lines that are long enough and either have a question mark or we can add one
                if line and len(line) > 10:
                    if not line.endswith('?'):
                        line += '?'
                    
                    suggestions.append(FollowUpSuggestion(
                        question=line,
                        category="llm_generated",
                        relevance=0.9 - (i * 0.05),
                        reason="Generato da LLM"
                    ))
                
                if len(suggestions) >= max_questions:
                    break
            
            if suggestions:
                return suggestions
            
        except Exception as e:
            log.warning(f"LLM follow-up generation failed: {e}")
        
        # Fallback to template-based
        return self.generate_template_based(query, response, max_questions)
    
    def format_for_display(
        self,
        suggestions: List[FollowUpSuggestion],
        style: str = "numbered"
    ) -> str:
        """
        Format suggestions for display.
        
        Args:
            suggestions: List of suggestions
            style: "numbered", "bullet", "emoji"
            
        Returns:
            Formatted string
        """
        if not suggestions:
            return ""
        
        lines = ["\n💡 **Possibili approfondimenti:**"]
        
        for i, sugg in enumerate(suggestions, 1):
            if style == "numbered":
                lines.append(f"{i}. {sugg.question}")
            elif style == "bullet":
                lines.append(f"• {sugg.question}")
            elif style == "emoji":
                emoji = "🔍" if sugg.category == "deepening" else "🔗" if sugg.category == "related" else "💼"
                lines.append(f"{emoji} {sugg.question}")
        
        return '\n'.join(lines)
    
    def to_telegram_buttons(
        self,
        suggestions: List[FollowUpSuggestion]
    ) -> List[Dict[str, str]]:
        """
        Convert suggestions to Telegram inline button format.
        
        Args:
            suggestions: List of suggestions
            
        Returns:
            List of button dicts for Telegram
        """
        buttons = []
        
        for sugg in suggestions:
            # Truncate question for button text
            text = sugg.question
            if len(text) > 50:
                text = text[:47] + "..."
            
            buttons.append({
                "text": text,
                "callback_data": f"followup:{sugg.question[:100]}"
            })
        
        return buttons


# === Singleton Instance ===
_generator_instance: Optional[FollowUpGenerator] = None


def get_followup_generator(llm_func=None) -> FollowUpGenerator:
    """
    Get or create FollowUpGenerator singleton.
    
    Args:
        llm_func: Optional LLM function
        
    Returns:
        FollowUpGenerator instance
    """
    global _generator_instance
    
    if _generator_instance is None:
        _generator_instance = FollowUpGenerator(llm_func=llm_func)
    elif llm_func and _generator_instance.llm_func is None:
        _generator_instance.llm_func = llm_func
    
    return _generator_instance


def generate_followups(
    query: str,
    response: str,
    max_questions: int = 3
) -> List[Dict[str, Any]]:
    """
    Utility function to generate follow-up questions.
    
    Args:
        query: Original query
        response: LLM response
        max_questions: Max questions to generate
        
    Returns:
        List of follow-up question dicts
    """
    generator = get_followup_generator()
    suggestions = generator.generate_template_based(query, response, max_questions)
    
    return [
        {
            "question": s.question,
            "category": s.category,
            "relevance": s.relevance,
        }
        for s in suggestions
    ]
