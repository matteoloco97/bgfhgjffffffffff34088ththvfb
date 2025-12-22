# core/fact_verifier.py - NEW FILE

from typing import List, Dict, Any
import re
from collections import Counter

class CrossSourceVerifier:
    """
    Verifica fatti attraverso cross-reference tra fonti multiple.
    Identifica informazioni concordi VS discordi.
    """
    
    def verify_facts(
        self, 
        extracts: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Analizza concordanza tra fonti.
        
        Returns:
            {
                "verified_facts": [...],  # Fatti presenti in 2+ fonti
                "single_source_facts": [...],  # Fatti da 1 sola fonte
                "conflicts": [...],  # Informazioni contraddittorie
                "confidence_score": float
            }
        """
        if len(extracts) < 2:
            return {
                "verified_facts": [],
                "single_source_facts": [],
                "conflicts": [],
                "confidence_score": 0.5
            }
        
        # 1. Estrai claim candidati (numeri, date, nomi)
        all_claims = []
        for ex in extracts:
            text = ex.get('text', '')
            claims = self._extract_claims(text)
            all_claims.extend([{
                "claim": c,
                "source_url": ex.get('url', ''),
                "source_idx": ex.get('index', 0)
            } for c in claims])
        
        # 2. Identifica claim ricorrenti (cross-verification)
        claim_texts = [c['claim'] for c in all_claims]
        claim_counts = Counter(claim_texts)
        
        verified = [
            claim for claim, count in claim_counts.items()
            if count >= 2
        ]
        
        single_source = [
            claim for claim, count in claim_counts.items()
            if count == 1
        ]
        
        # 3. Detect conflicts (stesso topic, valori diversi)
        conflicts = self._detect_conflicts(all_claims)
        
        # 4. Calculate confidence
        total_claims = len(claim_counts)
        verified_ratio = len(verified) / max(1, total_claims)
        conflict_penalty = len(conflicts) * 0.1
        
        confidence = max(0.0, min(1.0, verified_ratio - conflict_penalty))
        
        return {
            "verified_facts": verified[:10],
            "single_source_facts": single_source[:5],
            "conflicts": conflicts[:3],
            "confidence_score": round(confidence, 3),
            "total_claims_analyzed": total_claims
        }
    
    def _extract_claims(self, text: str) -> List[str]:
        """Estrai claim verificabili (numeri, date, percentuali, nomi propri)."""
        claims = []
        
        # Numeri con contesto
        for m in re.finditer(r'(\w+\s+(?:è|sono|costa|vale|misura))\s+([€$£]?\s*[\d,.]+\s*[%€$£]?)', text, re.I):
            claims.append(m.group(0).strip())
        
        # Date con eventi
        for m in re.finditer(r'(\w+\s+(?:il|nel|dal|al))\s+(\d{1,2}[/-]\d{1,2}[/-]\d{2,4}|\d{4})', text, re.I):
            claims.append(m.group(0).strip())
        
        # Nomi propri con predicati
        for m in re.finditer(r'\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)*)\s+(è|ha|sono|hanno)\s+(\w+(?:\s+\w+){0,3})', text):
            if len(m.group(0)) < 80:
                claims.append(m.group(0).strip())
        
        return claims[:20]  # Max 20 claims per documento
    
    def _detect_conflicts(self, all_claims: List[Dict]) -> List[Dict]:
        """Identifica claim contraddittori."""
        conflicts = []
        
        # Raggruppa per topic (primi 2-3 token)
        from collections import defaultdict
        by_topic = defaultdict(list)
        
        for claim_obj in all_claims:
            claim = claim_obj['claim']
            topic = ' '.join(claim.split()[:3]).lower()
            by_topic[topic].append(claim_obj)
        
        # Cerca valori numerici diversi nello stesso topic
        for topic, claims in by_topic.items():
            if len(claims) < 2:
                continue
            
            numbers = []
            for c in claims:
                nums = re.findall(r'[\d,.]+', c['claim'])
                if nums:
                    numbers.append({
                        "value": nums[0],
                        "claim": c['claim'],
                        "source": c['source_url']
                    })
            
            if len(numbers) >= 2:
                unique_values = set(n['value'] for n in numbers)
                if len(unique_values) > 1:
                    conflicts.append({
                        "topic": topic,
                        "conflicting_claims": [
                            f"{n['value']} (fonte: {n['source']})"
                            for n in numbers[:3]
                        ]
                    })
        
        return conflicts


# Integra nel synthesis prompt
SYNTHESIS_PROMPT_V3_WITH_VERIFICATION = """
... [prompt esistente] ...

=== INFORMAZIONI DI VERIFICA ===
{verification_info}

IMPORTANTE: 
- Privilegia i "fatti verificati" (presenti in 2+ fonti)
- Segnala esplicitamente se ci sono conflitti tra fonti
- I "fatti da singola fonte" vanno menzionati con cautela

... [resto del prompt] ...
"""
