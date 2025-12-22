# core/content_analyzer.py
# Utilità leggere per chunking testuale e estrazione claims/entità

import re
from typing import List, Dict

class ContentAnalyzer:
    def smart_chunk_text(self, text: str, max_tokens: int = 500) -> List[Dict]:
        """Chunking testuale semplice con heading fittizi.
        Divide per righe vuote / bullet / headings imitati.
        """
        if not text:
            return []
        blocks: List[str] = re.split(r"\n\s*\n+", text)
        out: List[Dict] = []
        buf = []
        tok = 0
        for b in blocks:
            b = b.strip()
            if not b:
                continue
            btok = max(1, (len(b) + 3) // 4)
            if tok + btok > max_tokens and buf:
                out.append({"content": "\n".join(buf)})
                buf, tok = [], 0
            buf.append(b)
            tok += btok
        if buf:
            out.append({"content": "\n".join(buf)})
        return out

    def extract_claims(self, text: str) -> List[str]:
        """Estrai frasi con verbi copulativi o quantitativi: proxy grezzo per claims fattuali."""
        sents = re.split(r"(?<=[.!?])\s+", text or "")
        verbs = (" è ", " sono ", " ha ", " hanno ", " costa ", " misura ", " contiene ", "%", "€")
        claims: List[str] = []
        for s in sents[:40]:
            sl = " " + s.lower() + " "
            if any(v in sl for v in verbs) and len(s.split()) >= 5:
                claims.append(s.strip())
        return claims
