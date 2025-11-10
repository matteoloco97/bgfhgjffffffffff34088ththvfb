# core/token_budget.py — stima token e taglio sicuro (grezzo ma veloce)
import math, re
CHARS_PER_TOKEN = 4  # stima prudente per modelli BPE

def approx_tokens(s: str) -> int:
    return math.ceil(len(s or "") / CHARS_PER_TOKEN)

def trim_to_tokens(s: str, max_tokens: int) -> str:
    if not s or max_tokens <= 0:
        return ""
    max_chars = max_tokens * CHARS_PER_TOKEN
    if len(s) <= max_chars:
        return s
    cut = s[:max_chars]
    # taglio “pulito” su fine frase, se presente
    m = re.search(r'(?s)^(.{0,' + str(max_chars) + r'}[.!?])\s', s)
    return m.group(1) if m else cut
