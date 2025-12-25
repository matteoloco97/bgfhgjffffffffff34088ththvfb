"""
Telegram Message Chunking Utility
Gestisce messaggi lunghi dividendoli in chunk intelligenti
"""

import re
from typing import List, Tuple

# Costanti Telegram
TELEGRAM_MAX_LENGTH = 4096
CHUNK_SAFE_SIZE = 3900  # Margine di sicurezza per metadata


class MessageChunker:
    """Gestisce la divisione intelligente di messaggi lunghi"""
    
    def __init__(self, max_length: int = CHUNK_SAFE_SIZE):
        self.max_length = max_length
    
    def split(self, text: str) -> List[str]:
        """
        Divide un messaggio lungo in chunk intelligenti.
        
        Priorità divisione:
        1. Sezioni markdown (##, ###)
        2. Paragrafi vuoti (\n\n)
        3. Singoli newline (\n)
        4. Frasi (. ! ?)
        5. Spazi
        6. Hard cut se necessario
        
        Args:
            text: Testo da dividere
            
        Returns:
            Lista di chunk, ciascuno <4096 caratteri
        """
        if len(text) <= self.max_length:
            return [text]
        
        chunks = []
        remaining = text
        
        while remaining:
            if len(remaining) <= self.max_length:
                chunks.append(remaining)
                break
            
            # Estrai chunk
            chunk, remaining = self._extract_chunk(remaining)
            chunks.append(chunk)
        
        return chunks
    
    def _extract_chunk(self, text: str) -> Tuple[str, str]:
        """Estrae un chunk dal testo rimanente"""
        
        # Lunghezza massima per questo chunk
        max_len = self.max_length
        
        if len(text) <= max_len:
            return text, ""
        
        # Prendi il testo fino al limite
        chunk = text[:max_len]
        
        # Cerca punti di divisione ottimali (dal più prioritario al meno)
        split_pos = self._find_best_split_point(chunk)
        
        # Dividi
        actual_chunk = text[:split_pos].rstrip()
        remaining = text[split_pos:].lstrip()
        
        return actual_chunk, remaining
    
    def _find_best_split_point(self, chunk: str) -> int:
        """Trova il miglior punto di divisione nel chunk"""
        
        max_len = len(chunk)
        
        # 1. Cerca sezioni markdown (##, ###, ecc)
        markdown_headers = list(re.finditer(r'\n#{1,6}\s', chunk))
        if markdown_headers:
            # Usa l'ultimo header che lascia almeno 60% del chunk
            for match in reversed(markdown_headers):
                pos = match.start()
                if pos > max_len * 0.6:
                    return pos
        
        # 2. Cerca doppio newline (paragrafo)
        split_pos = chunk.rfind('\n\n')
        if split_pos > max_len * 0.6:  # Almeno 60% del chunk
            return split_pos
        
        # 3. Cerca singolo newline
        split_pos = chunk.rfind('\n')
        if split_pos > max_len * 0.5:  # Almeno 50% del chunk
            return split_pos
        
        # 4. Cerca fine frase (. ! ?)
        sentence_end = max(
            chunk.rfind('. '),
            chunk.rfind('! '),
            chunk.rfind('? ')
        )
        if sentence_end > max_len * 0.4:  # Almeno 40% del chunk
            return sentence_end + 1  # Include il punto
        
        # 5. Cerca spazio
        split_pos = chunk.rfind(' ')
        if split_pos > max_len * 0.3:  # Almeno 30% del chunk
            return split_pos
        
        # 6. Hard cut (ultima risorsa)
        return max_len
    
    def add_continuation_markers(self, chunks: List[str]) -> List[str]:
        """Aggiunge marker di continuazione ai chunk multipli"""
        
        if len(chunks) <= 1:
            return chunks
        
        marked_chunks = []
        
        for i, chunk in enumerate(chunks):
            if i == 0:
                # Primo chunk: aggiungi solo indicatore fine
                marked_chunks.append(chunk + "\n\n📝 _(continua...)_")
            elif i == len(chunks) - 1:
                # Ultimo chunk: aggiungi solo indicatore inizio
                marked_chunks.append(f"📝 _(continua...)\n\n{chunk}")
            else:
                # Chunk intermedi: entrambi gli indicatori
                marked_chunks.append(f"📝 _(continua...)\n\n{chunk}\n\n📝 _(continua...)_")
        
        return marked_chunks


# Singleton globale
_chunker = MessageChunker()


def split_message(text: str, add_markers: bool = True) -> List[str]:
    """
    Funzione helper per dividere un messaggio.
    
    Args:
        text: Messaggio da dividere
        add_markers: Se True, aggiunge marker di continuazione
        
    Returns:
        Lista di chunk pronti per l'invio
    """
    chunks = _chunker.split(text)
    
    if add_markers and len(chunks) > 1:
        chunks = _chunker.add_continuation_markers(chunks)
    
    return chunks


# Test rapido
if __name__ == "__main__":
    # Test con messaggio lungo
    test_text = """
# Titolo Principale

Questo è un paragrafo introduttivo molto lungo che contiene diverse informazioni importanti.

## Sezione 1

Primo paragrafo della sezione 1 con molte informazioni dettagliate.

Secondo paragrafo della sezione 1.

## Sezione 2

Contenuto della sezione 2.
""" * 10  # Ripeti per farlo diventare lungo
    
    chunks = split_message(test_text, add_markers=True)
    
    print(f"Testo originale: {len(test_text)} caratteri")
    print(f"Diviso in {len(chunks)} chunk:")
    for i, chunk in enumerate(chunks, 1):
        print(f"\n--- Chunk {i} ({len(chunk)} caratteri) ---")
        print(chunk[:200] + "..." if len(chunk) > 200 else chunk)
