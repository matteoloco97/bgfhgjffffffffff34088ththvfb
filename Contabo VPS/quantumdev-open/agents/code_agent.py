#!/usr/bin/env python3
"""
agents/code_agent.py
====================

Agente codice dedicato per Jarvis.
Gestisce richieste di generazione, debug, test e documentazione codice.

Funzionalità:
- Generazione codice strutturata con piano + implementazione
- Debug e fix di errori
- Test generation
- Code review
- Documentazione

Formato risposta standardizzato:
- Piano in passi chiari
- Codice completo e funzionante
- Istruzioni di esecuzione (3-5 passi)
"""

import asyncio
import logging
import re
import os
from typing import Optional, Dict, Any, List, Tuple
from datetime import datetime

log = logging.getLogger(__name__)

# ===================== CONFIG =====================

CODE_AGENT_TIMEOUT = float(os.getenv("CODE_AGENT_TIMEOUT", "30.0"))
CODE_MAX_TOKENS = int(os.getenv("CODE_MAX_TOKENS", "2048"))

# ===================== LANGUAGE MAPPING =====================

# Mapping linguaggi supportati
LANGUAGE_ALIASES: Dict[str, str] = {
    # Python
    "python": "python",
    "py": "python",
    "python3": "python",
    # JavaScript
    "javascript": "javascript",
    "js": "javascript",
    "node": "javascript",
    "nodejs": "javascript",
    # TypeScript
    "typescript": "typescript",
    "ts": "typescript",
    # Java
    "java": "java",
    # C/C++
    "c": "c",
    "c++": "cpp",
    "cpp": "cpp",
    # C#
    "c#": "csharp",
    "csharp": "csharp",
    # Go
    "go": "go",
    "golang": "go",
    # Rust
    "rust": "rust",
    "rs": "rust",
    # Shell/Bash
    "bash": "bash",
    "shell": "bash",
    "sh": "bash",
    # SQL
    "sql": "sql",
    "mysql": "sql",
    "postgresql": "sql",
    "postgres": "sql",
    # Web
    "html": "html",
    "css": "css",
    # Other
    "ruby": "ruby",
    "php": "php",
    "swift": "swift",
    "kotlin": "kotlin",
}

# File extension mapping
LANGUAGE_EXTENSIONS: Dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "c": ".c",
    "cpp": ".cpp",
    "csharp": ".cs",
    "go": ".go",
    "rust": ".rs",
    "bash": ".sh",
    "sql": ".sql",
    "html": ".html",
    "css": ".css",
    "ruby": ".rb",
    "php": ".php",
    "swift": ".swift",
    "kotlin": ".kt",
}

# ===================== CODE REQUEST TYPES =====================

CODE_REQUEST_TYPES: Dict[str, List[str]] = {
    "generate": [
        "scrivi", "genera", "crea", "implementa", "programma",
        "write", "generate", "create", "implement", "code",
        "funzione che", "classe che", "script che",
        "function that", "class that", "script that",
    ],
    "debug": [
        "debug", "debugga", "fixa", "fix", "correggi", "ripara",
        "errore", "error", "bug", "problema", "non funziona",
        "doesn't work", "not working", "broken",
    ],
    "explain": [
        "spiega", "explain", "cosa fa", "what does",
        "come funziona", "how does", "analizza", "analyze",
    ],
    "optimize": [
        "ottimizza", "optimize", "migliora", "improve",
        "refactor", "refactora", "rendi più veloce", "make faster",
    ],
    "test": [
        "test", "testa", "unit test", "testing",
        "scrivi test", "write test", "genera test",
    ],
    "document": [
        "documenta", "document", "commenta", "comment",
        "docstring", "readme", "documentazione",
    ],
}

# ===================== PROMPT BUILDERS =====================


def _build_generation_prompt(
    description: str,
    language: str,
    context: str = "",
) -> str:
    """
    Costruisce prompt per generazione codice.
    """
    lang_display = language.capitalize() if language else "appropriato"
    
    prompt = f"""Sei Jarvis, assistente di programmazione esperto. Genera codice {lang_display} per la seguente richiesta.

=== RICHIESTA ===
{description}

=== REGOLE ===
1. Genera codice COMPLETO e FUNZIONANTE, non placeholder o "..." 
2. Includi TUTTI gli import/require necessari
3. Aggiungi commenti inline per le parti importanti
4. Usa best practices e naming conventions standard
5. Gestisci gli errori in modo appropriato

=== FORMATO RISPOSTA ===

📌 **[Titolo breve del componente]**

**📋 Piano:**
1. [Passo 1]
2. [Passo 2]
3. [Passo 3]

**💻 Codice:**
```{language or 'python'}
[codice completo qui]
```

**🚀 Come usarlo:**
1. [Passo 1 per eseguire]
2. [Passo 2]
3. [Passo 3]

**⚠️ Note:**
• [Eventuali dipendenze da installare]
• [Limitazioni o considerazioni]
"""

    if context:
        prompt += f"\n=== CONTESTO AGGIUNTIVO ===\n{context}\n"
    
    prompt += "\nGENERA ORA:"
    
    return prompt


def _build_debug_prompt(
    code: str,
    error_message: str,
    description: str = "",
) -> str:
    """
    Costruisce prompt per debug di codice.
    """
    prompt = f"""Sei Jarvis, esperto debugger. Analizza e correggi il seguente codice.

=== CODICE CON ERRORE ===
```
{code}
```

=== ERRORE ===
{error_message}

"""
    
    if description:
        prompt += f"=== DESCRIZIONE PROBLEMA ===\n{description}\n\n"
    
    prompt += """=== REGOLE ===
1. Identifica la CAUSA ESATTA dell'errore
2. Fornisci il codice CORRETTO e completo
3. Spiega cosa era sbagliato e perché
4. Se ci sono altri potenziali problemi, segnalali

=== FORMATO RISPOSTA ===

🔧 **Debug: [breve descrizione problema]**

**❌ Problema identificato:**
[Spiegazione chiara del bug]

**✅ Codice corretto:**
```
[codice fixato qui]
```

**📝 Cosa è cambiato:**
• [Modifica 1 e perché]
• [Modifica 2 e perché]

**⚠️ Suggerimenti aggiuntivi:**
• [Altri miglioramenti possibili]

ANALIZZA E CORREGGI ORA:"""
    
    return prompt


def _build_explain_prompt(code: str, language: str = "") -> str:
    """
    Costruisce prompt per spiegazione codice.
    """
    prompt = f"""Sei Jarvis, esperto programmatore. Spiega il seguente codice in modo chiaro.

=== CODICE DA SPIEGARE ===
```{language}
{code}
```

=== REGOLE ===
1. Spiega cosa fa il codice nel complesso
2. Analizza ogni parte importante
3. Identifica pattern e tecniche usate
4. Evidenzia potenziali problemi o miglioramenti

=== FORMATO RISPOSTA ===

📖 **Spiegazione Codice**

**🎯 Scopo generale:**
[Cosa fa questo codice in 1-2 frasi]

**🔍 Analisi dettagliata:**
• [Parte 1]: [spiegazione]
• [Parte 2]: [spiegazione]
• [Parte 3]: [spiegazione]

**🛠️ Tecniche usate:**
• [Tecnica/pattern 1]
• [Tecnica/pattern 2]

**⚠️ Note/Suggerimenti:**
• [Potenziali miglioramenti]
• [Cose da tenere a mente]

SPIEGA ORA:"""
    
    return prompt


def _build_test_prompt(code: str, language: str = "python") -> str:
    """
    Costruisce prompt per generazione test.
    """
    prompt = f"""Sei Jarvis, esperto di testing. Genera test unitari per il seguente codice.

=== CODICE DA TESTARE ===
```{language}
{code}
```

=== REGOLE ===
1. Genera test COMPLETI che coprono i casi principali
2. Includi test per casi limite (edge cases)
3. Includi test per gestione errori
4. Usa il framework di test standard per il linguaggio

=== FORMATO RISPOSTA ===

🧪 **Test Suite**

**📋 Casi di test:**
• [Caso 1]: [cosa testa]
• [Caso 2]: [cosa testa]
• [Caso 3]: [cosa testa]

**💻 Codice test:**
```{language}
[codice test completo]
```

**🚀 Come eseguire:**
1. [Comando per eseguire i test]

**⚠️ Copertura:**
• [Quali scenari sono coperti]
• [Eventuali scenari da aggiungere]

GENERA TEST ORA:"""
    
    return prompt


# ===================== QUERY EXTRACTION =====================


def extract_language(query: str) -> Optional[str]:
    """
    Estrae il linguaggio di programmazione dalla query.
    """
    q = query.lower()
    
    # Check aliases diretti
    for alias, lang in LANGUAGE_ALIASES.items():
        # Pattern: "in python", "python script", "codice python"
        patterns = [
            rf"\b{alias}\b",
            rf"in\s+{alias}",
            rf"{alias}\s+script",
            rf"codice\s+{alias}",
        ]
        for pattern in patterns:
            if re.search(pattern, q):
                return lang
    
    # Default a Python se non specificato
    return None


def extract_code_block(text: str) -> Optional[str]:
    """
    Estrae un blocco di codice dalla query.
    """
    # Pattern per code blocks markdown
    match = re.search(r"```(?:\w+)?\s*\n?(.*?)```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    
    # Pattern per codice inline
    match = re.search(r"`([^`]+)`", text)
    if match:
        return match.group(1).strip()
    
    return None


def extract_code_request_type(query: str) -> str:
    """
    Determina il tipo di richiesta codice.
    """
    q = query.lower()
    
    for req_type, keywords in CODE_REQUEST_TYPES.items():
        if any(kw in q for kw in keywords):
            return req_type
    
    # Default a generazione
    return "generate"


def is_code_query(query: str) -> bool:
    """
    Determina se la query è una richiesta di coding.
    """
    q = query.lower().strip()
    
    # Check espliciti
    code_indicators = [
        "scrivi codice", "genera codice", "crea script",
        "scrivi uno script", "genera uno script",
        "scrivi un programma", "crea un programma",
        "implementa", "programma che", "script che",
        "funzione che", "classe che", "metodo che",
        "codice python", "codice javascript", "codice java",
        "script bash", "script python", "script shell",
        "write code", "generate code", "create script",
        "debug", "fixa", "fix", "correggi",
        "refactor", "ottimizza codice",
        "unit test", "scrivi test",
    ]
    
    if any(ind in q for ind in code_indicators):
        return True
    
    # Check per blocchi di codice nella query (richiesta di debug/explain)
    if "```" in q or re.search(r"`[^`]+`", q):
        return True
    
    # Check linguaggi + verbo azione
    action_verbs = ["scrivi", "genera", "crea", "implementa", "fixa", "debug"]
    for lang in LANGUAGE_ALIASES:
        if lang in q and any(v in q for v in action_verbs):
            return True
    
    return False


# ===================== PUBLIC API =====================


async def generate_code_response(
    query: str,
    llm_func=None,
    persona: str = "",
) -> str:
    """
    API principale: genera risposta strutturata per richieste di coding.
    
    Args:
        query: Richiesta utente
        llm_func: Funzione async per chiamare LLM (es. reply_with_llm)
        persona: Persona/system prompt opzionale
    
    Returns:
        Risposta formattata con codice
    """
    # Estrai info dalla query
    language = extract_language(query) or "python"
    code_block = extract_code_block(query)
    request_type = extract_code_request_type(query)
    
    log.info(f"Code request: type={request_type}, lang={language}")
    
    # Costruisci prompt appropriato
    if request_type == "debug" and code_block:
        # Cerca messaggio di errore
        error_match = re.search(r"(error|errore|exception|traceback)[:\s]+(.+)", query, re.IGNORECASE)
        error_msg = error_match.group(2) if error_match else "Errore non specificato"
        prompt = _build_debug_prompt(code_block, error_msg, query)
        
    elif request_type == "explain" and code_block:
        prompt = _build_explain_prompt(code_block, language)
        
    elif request_type == "test" and code_block:
        prompt = _build_test_prompt(code_block, language)
        
    else:
        # Default: generazione codice
        prompt = _build_generation_prompt(query, language)
    
    # Chiama LLM
    if llm_func:
        try:
            response = await asyncio.wait_for(
                llm_func(prompt, persona),
                timeout=CODE_AGENT_TIMEOUT
            )
            return response
        except asyncio.TimeoutError:
            return "❌ Timeout nella generazione del codice. Riprova con una richiesta più semplice."
        except Exception as e:
            log.error(f"Code agent LLM error: {e}")
            return f"❌ Errore nella generazione: {e}"
    
    # Se non c'è funzione LLM, ritorna il prompt (per debug)
    return prompt


async def get_code_for_query(query: str, llm_func=None, persona: str = "") -> Optional[str]:
    """
    Wrapper: verifica se è una code query e restituisce la risposta.
    """
    if not is_code_query(query):
        return None
    
    return await generate_code_response(query, llm_func, persona)


# ===================== HELPER FUNCTIONS =====================


def format_code_response_simple(
    title: str,
    code: str,
    language: str = "python",
    instructions: List[str] = None,
    notes: List[str] = None,
) -> str:
    """
    Helper per formattare una risposta codice semplice.
    Utile per altri moduli che vogliono usare lo stesso formato.
    """
    lines = [f"📌 **{title}**\n"]
    
    lines.append(f"**💻 Codice:**")
    lines.append(f"```{language}")
    lines.append(code)
    lines.append("```\n")
    
    if instructions:
        lines.append("**🚀 Come usarlo:**")
        for i, inst in enumerate(instructions, 1):
            lines.append(f"{i}. {inst}")
        lines.append("")
    
    if notes:
        lines.append("**⚠️ Note:**")
        for note in notes:
            lines.append(f"• {note}")
    
    return "\n".join(lines)
