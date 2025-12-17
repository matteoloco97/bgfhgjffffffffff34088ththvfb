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

CODE_AGENT_TIMEOUT = float(os.getenv("CODE_AGENT_TIMEOUT", "60.0"))
CODE_MAX_TOKENS = int(os.getenv("CODE_MAX_TOKENS", "8192"))
CODE_TEMPERATURE = float(os.getenv("CODE_TEMPERATURE", "0.3"))  # Lower for more precise code

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
    Costruisce prompt ottimizzato per generazione codice di alta qualità.
    
    Ottimizzato per:
    - Codice production-ready
    - Best practices e pattern moderni
    - Error handling robusto
    - Type hints e documentazione
    """
    lang_display = language.capitalize() if language else "appropriato"
    
    # Language-specific best practices
    lang_hints = {
        "python": """
- Usa type hints (Python 3.10+)
- Segui PEP 8 e PEP 257 (docstrings)
- Usa context managers (with) per risorse
- Preferisci f-strings per formattazione
- Usa async/await se appropriato""",
        "javascript": """
- Usa ES6+ syntax (const, let, arrow functions)
- Preferisci async/await a callbacks
- Usa destructuring dove appropriato
- Aggiungi JSDoc comments
- Gestisci errori con try/catch""",
        "typescript": """
- Usa TypeScript strict mode patterns
- Definisci interface/type per ogni struttura dati
- Evita 'any', usa tipi specifici
- Usa generics dove appropriato
- Aggiungi JSDoc/TSDoc comments""",
        "go": """
- Segui Go idioms (error handling esplicito)
- Usa defer per cleanup
- Preferisci composition a inheritance
- Documenta con GoDoc style
- Gestisci errori con if err != nil""",
        "rust": """
- Usa Result<T, E> per error handling
- Preferisci ownership e borrowing corretti
- Usa match per pattern matching
- Documenta con rustdoc
- Usa #[derive] appropriatamente""",
    }
    
    lang_specific = lang_hints.get(language, "- Segui le best practices del linguaggio")
    
    prompt = f"""Sei un Senior Software Engineer con 15+ anni di esperienza. Genera codice {lang_display} di qualità PRODUCTION-READY.

=== RICHIESTA ===
{description}

=== REQUISITI DI QUALITÀ ===

**CODICE:**
1. ✅ Codice COMPLETO, FUNZIONANTE e TESTABILE - MAI placeholder o "..."
2. ✅ TUTTI gli import/require necessari all'inizio
3. ✅ Error handling robusto (try/catch, Result types, etc.)
4. ✅ Input validation dove appropriato
5. ✅ Naming chiaro e descrittivo (no abbreviazioni criptiche)

**BEST PRACTICES {lang_display.upper()}:**
{lang_specific}

**STRUTTURA:**
1. Modularità: funzioni piccole con responsabilità singola
2. Riutilizzabilità: parametri configurabili, no valori hardcoded
3. Leggibilità: codice auto-documentante + commenti per logica complessa
4. Performance: algoritmi efficienti, evita operazioni O(n²) inutili

=== FORMATO RISPOSTA ===

📌 **[Nome descrittivo del componente]**

**📋 Architettura:**
1. [Componente/Funzione principale]
2. [Helper functions]
3. [Data structures]

**💻 Codice:**
```{language or 'python'}
[codice completo qui - NESSUN placeholder]
```

**🧪 Esempio d'uso:**
```{language or 'python'}
[esempio pratico di come usare il codice]
```

**🚀 Setup:**
1. [Dipendenze da installare: `pip install X` / `npm install X`]
2. [Configurazione necessaria]
3. [Come eseguire]

**⚠️ Note importanti:**
• [Limitazioni note]
• [Edge cases da considerare]
• [Suggerimenti per estensione futura]
"""

    if context:
        prompt += f"\n=== CONTESTO AGGIUNTIVO ===\n{context}\n"
    
    prompt += "\n🎯 GENERA CODICE PRODUCTION-READY ORA:"
    
    return prompt


def _build_debug_prompt(
    code: str,
    error_message: str,
    description: str = "",
) -> str:
    """
    Costruisce prompt avanzato per debug e fix di codice.
    
    Usa analisi multi-step per identificare root cause.
    """
    prompt = f"""Sei un Senior Debugger con expertise in analisi di codice e root cause analysis.

=== CODICE DA ANALIZZARE ===
```
{code}
```

=== ERRORE/PROBLEMA ===
{error_message}

"""
    
    if description:
        prompt += f"=== CONTESTO AGGIUNTIVO ===\n{description}\n\n"
    
    prompt += """=== PROCESSO DI DEBUG ===

**STEP 1 - Analisi dell'errore:**
- Tipo di errore (syntax, runtime, logic, type)
- Stack trace analysis (se disponibile)
- Linea/e coinvolte

**STEP 2 - Root Cause Analysis:**
- Perché questo errore si verifica?
- Quali assunzioni sono state violate?
- Ci sono problemi di stato o race conditions?

**STEP 3 - Fix e Prevenzione:**
- Correggi il bug specifico
- Aggiungi validazione input se mancante
- Migliora error handling
- Suggerisci test per prevenire regressioni

=== FORMATO RISPOSTA ===

🔧 **Debug Report: [tipo di bug]**

**🔍 Analisi:**
• Tipo errore: [syntax/runtime/logic/type]
• Causa root: [spiegazione concisa]
• Linee coinvolte: [numeri linea]

**❌ Problema:**
[Spiegazione dettagliata del bug - cosa accade e perché]

**✅ Codice Corretto:**
```
[codice COMPLETO fixato - non solo lo snippet]
```

**📝 Modifiche Applicate:**
1. [Modifica 1]: [perché necessaria]
2. [Modifica 2]: [perché necessaria]

**🛡️ Prevenzione Futura:**
• [Come evitare questo bug in futuro]
• [Test case suggerito]

**⚠️ Attenzione:**
• [Altri potenziali problemi trovati durante l'analisi]
"""
    
    prompt += "\n🎯 ANALIZZA E CORREGGI ORA:"
    
    return prompt


def _build_explain_prompt(code: str, language: str = "") -> str:
    """
    Costruisce prompt per spiegazione codice dettagliata.
    
    Produce analisi multi-livello con focus su comprensione e apprendimento.
    """
    prompt = f"""Sei un Software Architect esperto in code review e mentoring.

=== CODICE DA ANALIZZARE ===
```{language}
{code}
```

=== ANALISI RICHIESTA ===

Fornisci una spiegazione completa a tre livelli:
1. **Alto livello**: Cosa fa il codice e perché
2. **Medio livello**: Struttura e flusso di esecuzione
3. **Basso livello**: Dettagli implementativi importanti

=== FORMATO RISPOSTA ===

📖 **Code Analysis Report**

**🎯 Overview:**
[Cosa fa questo codice - 2-3 frasi chiare]

**📊 Struttura:**
```
[ASCII diagram del flusso/architettura se appropriato]
```

**🔍 Analisi Linea per Linea:**

| Sezione | Linee | Descrizione |
|---------|-------|-------------|
| [Nome] | [X-Y] | [Cosa fa] |

**🛠️ Pattern e Tecniche:**
• [Pattern 1]: [spiegazione e perché è usato]
• [Pattern 2]: [spiegazione e perché è usato]

**⚡ Complessità:**
• Time: O([...])
• Space: O([...])

**✅ Punti di Forza:**
• [Cosa è fatto bene]

**⚠️ Potenziali Miglioramenti:**
• [Suggerimento 1]
• [Suggerimento 2]

**📚 Concetti Chiave da Capire:**
• [Concetto 1]: [breve spiegazione]
• [Concetto 2]: [breve spiegazione]

🎯 ANALIZZA ORA:"""
    
    return prompt


def _build_test_prompt(code: str, language: str = "python") -> str:
    """
    Costruisce prompt per generazione test completi.
    
    Genera test suite con copertura completa.
    """
    # Test framework per linguaggio
    test_frameworks = {
        "python": "pytest (preferito) o unittest",
        "javascript": "Jest o Mocha/Chai",
        "typescript": "Jest con ts-jest",
        "go": "testing package nativo",
        "rust": "cargo test",
        "java": "JUnit 5",
        "csharp": "xUnit o NUnit",
    }
    
    framework = test_frameworks.get(language, "framework standard del linguaggio")
    
    prompt = f"""Sei un QA Engineer senior specializzato in test-driven development.

=== CODICE DA TESTARE ===
```{language}
{code}
```

=== REQUISITI TEST SUITE ===

**Framework:** {framework}

**Tipi di Test Richiesti:**
1. ✅ Unit test per ogni funzione/metodo pubblico
2. ✅ Test per casi normali (happy path)
3. ✅ Test per edge cases (valori limite, empty, null)
4. ✅ Test per error handling (eccezioni, errori attesi)
5. ✅ Test per validazione input

**Best Practices:**
- Naming: test_[funzione]_[scenario]_[risultato atteso]
- Arrange-Act-Assert pattern
- Un assert per test (quando possibile)
- Mock dipendenze esterne
- Test isolati e indipendenti

=== FORMATO RISPOSTA ===

🧪 **Test Suite Completa**

**📊 Coverage Matrix:**

| Funzione | Happy Path | Edge Cases | Errors |
|----------|------------|------------|--------|
| [nome]   | ✅/❌      | ✅/❌      | ✅/❌   |

**📋 Test Cases:**
1. `test_[nome]`: [descrizione]
2. `test_[nome]`: [descrizione]
3. `test_[nome]`: [descrizione]

**💻 Codice Test:**
```{language}
[test suite COMPLETA - non abbreviare]
```

**🚀 Esecuzione:**
```bash
[comando per eseguire i test]
```

**📈 Copertura Stimata:**
• Linee: ~[X]%
• Branch: ~[X]%
• Scenari mancanti: [elenco]

**💡 Suggerimenti:**
• [Test aggiuntivi consigliati]
• [Miglioramenti al codice per testabilità]

🎯 GENERA TEST SUITE ORA:"""
    
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
