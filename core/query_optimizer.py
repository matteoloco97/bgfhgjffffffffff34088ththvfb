# Core/query_optimizer.py - NEW FILE

class QueryOptimizer:
    """
    Ottimizza query per massimizzare recall senza usare LLM.
    """
    
    def expand_query(self, query: str) -> List[str]:
        """
        Genera varianti della query per coverage migliore.
        """
        variants = [query]  # Original
        
        # Add year if about recent events
        current_year = datetime.now().year
        if any(w in query.lower() for w in ['oggi', 'adesso', 'ora', 'corrente']):
            variants.append(f"{query} {current_year}")
        
        # Add location if implicit
        if 'meteo' in query.lower() and 'italia' not in query.lower():
            variants.append(f"{query} italia")
        
        # Add "ultime notizie" for news queries
        if any(w in query.lower() for w in ['chi è', 'cosa', 'risultati']):
            variants.append(f"{query} ultime notizie")
        
        # Add synonyms for key terms
        synonyms = {
            'prezzo': ['quotazione', 'valore', 'costo'],
            'risultati': ['punteggio', 'score', 'classifica'],
            # ... more
        }
        
        for term, syns in synonyms.items():
            if term in query.lower():
                for syn in syns[:1]:  # Max 1 synonym to avoid explosion
                    variants.append(query.lower().replace(term, syn))
        
        return variants[:3]  # Max 3 variants to avoid over-fetching
