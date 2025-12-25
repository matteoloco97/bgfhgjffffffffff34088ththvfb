#!/usr/bin/env python3
# core/synthesis_validator.py — Validazione qualità sintesi web
# Rileva risposte evasive e valida presenza di facts concreti

from __future__ import annotations
import re
import logging
from typing import Dict, List, Any, Optional

log = logging.getLogger(__name__)

# === BAD PATTERNS (risposte da rigettare) ===
BAD_PATTERNS = [
    # Evasioni dirette
    r"non.*abbastanza.*informazion",
    r"non.*sufficien.*informazion",
    r"le\s+fonti\s+(non\s+)?contengon[oi].*sufficien",
    r"consulta.*font[ei]",
    r"apri.*font[e]",
    r"visit[a].*sit[oi]",
    r"per\s+maggiori\s+dettagli.*font",
    r"non\s+posso\s+rispondere",
    r"non\s+ho\s+abbastanza",
    
    # Frasi vaghe
    r"potrebb[e].*essere.*utile.*consultare",
    r"ti\s+consiglio\s+di\s+(aprire|visitare|consultare)",
    r"per\s+informazioni\s+aggiornate.*consult",
    r"verifica\s+direttamente",
    
    # Scuse generiche
    r"sfortunatamente.*non",
    r"purtroppo.*non",
    r"mi\s+dispiace.*non",
]

# === QUALITY INDICATORS (presenza richiesta) ===
FACT_PATTERNS = [
    r'\d+',                              # Numeri
    r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}',  # Date
    r'[€$£¥]\s*\d+',                     # Prezzi con simbolo
    r'\d+\s*[€$£¥]',                     # Prezzi simbolo dopo
    r'\d+\s*(kg|m|km|g|l|ml)',          # Unità misura
    r'\d+\s*%',                          # Percentuali
    r'[A-Z][a-z]+\s+[A-Z][a-z]+',       # Nomi propri (es. Elon Musk)
]

# === MIN REQUIREMENTS ===
MIN_LENGTH_CHARS = 80
MIN_SENTENCES = 2
MIN_FACTS = 2


class SynthesisValidator:
    """
    Validatore qualità sintesi web.
    
    Verifica:
    1. Assenza pattern evasivi
    2. Presenza facts concreti (numeri, date, nomi)
    3. Lunghezza minima ragionevole
    4. Struttura discorsiva
    """
    
    def __init__(
        self,
        min_length: int = MIN_LENGTH_CHARS,
        min_sentences: int = MIN_SENTENCES,
        min_facts: int = MIN_FACTS,
    ):
        self.min_length = min_length
        self.min_sentences = min_sentences
        self.min_facts = min_facts
        
        # Compile patterns
        self.bad_patterns_compiled = [re.compile(p, re.IGNORECASE) for p in BAD_PATTERNS]
        self.fact_patterns_compiled = [re.compile(p) for p in FACT_PATTERNS]
    
    def validate(self, text: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """
        Valida qualità sintesi.
        
        Args:
            text: Testo sintesi da validare
            context: Contesto opzionale (query, sources, etc.)
        
        Returns:
            {
                "valid": bool,
                "score": float,  # 0-1
                "issues": [str],
                "facts_count": int,
                "length": int,
                "suggestions": [str],
            }
        """
        text = (text or "").strip()
        issues = []
        suggestions = []
        
        # === CHECK 1: Lunghezza ===
        length_ok = len(text) >= self.min_length
        if not length_ok:
            issues.append(f"too_short_{len(text)}_chars")
            suggestions.append(f"Espandi la risposta (min {self.min_length} caratteri)")
        
        # === CHECK 2: Pattern evasivi ===
        bad_matches = []
        for pattern in self.bad_patterns_compiled:
            matches = pattern.findall(text)
            if matches:
                bad_matches.extend(matches)
        
        if bad_matches:
            issues.append(f"evasive_patterns_{len(bad_matches)}")
            suggestions.append(
                f"Rimuovi frasi evasive come: {', '.join(bad_matches[:3])}"
            )
        
        # === CHECK 3: Facts count ===
        facts_found = []
        for pattern in self.fact_patterns_compiled:
            facts_found.extend(pattern.findall(text))
        
        facts_count = len(facts_found)
        facts_ok = facts_count >= self.min_facts
        
        if not facts_ok:
            issues.append(f"insufficient_facts_{facts_count}")
            suggestions.append(
                f"Aggiungi più dettagli concreti (numeri, date, nomi). "
                f"Trovati {facts_count}, richiesti {self.min_facts}"
            )
        
        # === CHECK 4: Struttura frasi ===
        sentences = re.split(r'[.!?]+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentences_ok = len(sentences) >= self.min_sentences
        
        if not sentences_ok:
            issues.append(f"insufficient_sentences_{len(sentences)}")
            suggestions.append(
                f"Articola meglio in frasi separate (min {self.min_sentences})"
            )
        
        # === CHECK 5: Non solo liste ===
        # Se >70% del testo sono bullet points, segnala
        lines = text.split('\n')
        bullet_lines = sum(1 for line in lines if re.match(r'^\s*[-•*]\s', line))
        if lines and bullet_lines / len(lines) > 0.7:
            issues.append("mostly_bullets")
            suggestions.append("Usa forma discorsiva, non solo elenchi puntati")
        
        # === SCORE FINALE ===
        checks = [length_ok, not bad_matches, facts_ok, sentences_ok]
        score = sum(checks) / len(checks)
        
        valid = score >= 0.75  # Almeno 3/4 checks passati
        
        result = {
            "valid": valid,
            "score": round(score, 3),
            "issues": issues,
            "facts_count": facts_count,
            "length": len(text),
            "sentences_count": len(sentences),
            "suggestions": suggestions,
        }
        
        # Log se non valido
        if not valid:
            log.warning(f"Synthesis validation failed: score={score:.2f}, issues={issues}")
        
        return result
    
    def extract_bad_phrases(self, text: str) -> List[str]:
        """Estrae frasi problematiche dal testo"""
        bad_phrases = []
        for pattern in self.bad_patterns_compiled:
            # Trova contesto intorno al match (30 char prima/dopo)
            for match in pattern.finditer(text):
                start = max(0, match.start() - 30)
                end = min(len(text), match.end() + 30)
                context = text[start:end].strip()
                bad_phrases.append(context)
        return bad_phrases[:5]  # Max 5 esempi


# === Singleton ===
_GLOBAL_VALIDATOR: Optional[SynthesisValidator] = None

def get_synthesis_validator() -> SynthesisValidator:
    """Ottieni singleton validator"""
    global _GLOBAL_VALIDATOR
    if _GLOBAL_VALIDATOR is None:
        _GLOBAL_VALIDATOR = SynthesisValidator()
    return _GLOBAL_VALIDATOR
