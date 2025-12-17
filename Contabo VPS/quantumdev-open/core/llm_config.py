#!/usr/bin/env python3
"""
core/llm_config.py
==================
Preset configurazioni LLM ottimizzate per diversi task.

Questo modulo fornisce configurazioni predefinite ottimizzate per vari scenari
di utilizzo dell'LLM, con focus particolare sulla web synthesis ad alta velocità.
"""

from __future__ import annotations

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, asdict


@dataclass
class LLMPreset:
    """Preset configurazione LLM per task specifico.
    
    Attributes
    ----------
    temperature : float
        Controllo della creatività (0.0 = deterministica, 1.0 = creativa).
    max_tokens : int
        Numero massimo di token da generare.
    stop_sequences : List[str]
        Sequenze che fermano la generazione.
    repetition_penalty : float
        Penalità per ripetizioni (1.0 = nessuna penalità).
    presence_penalty : float
        Penalità per presenza di token già usati.
    top_p : float
        Nucleus sampling threshold (0.0-1.0).
    description : str
        Descrizione del preset e del suo uso.
    """
    
    temperature: float
    max_tokens: int
    stop_sequences: List[str]
    repetition_penalty: float
    presence_penalty: float
    top_p: float
    description: str


# Preset ottimizzati per diversi task
PRESETS: Dict[str, LLMPreset] = {
    "web_synthesis": LLMPreset(
        temperature=0.2,  # Bassa per consistenza e velocità
        max_tokens=120,   # Hard limit per velocità (max 50 parole)
        stop_sequences=["---", "\n\n\n", "Fonte:", "Fonti:", "Sources:", "###"],
        repetition_penalty=1.1,
        presence_penalty=0.6,
        top_p=0.9,
        description="Ultra-concise web synthesis (max 50 words, optimized for speed)"
    ),
    
    "chat": LLMPreset(
        temperature=0.75,  # Leggermente più creativo
        max_tokens=2048,   # Risposte più complete (aumentato da 512)
        stop_sequences=[],
        repetition_penalty=1.0,
        presence_penalty=0.0,
        top_p=0.95,
        description="Standard conversational chat with extended responses"
    ),
    
    "chat_extended": LLMPreset(
        temperature=0.7,
        max_tokens=4096,   # Per risposte molto lunghe e articolate
        stop_sequences=[],
        repetition_penalty=1.02,
        presence_penalty=0.1,
        top_p=0.95,
        description="Extended chat for complex topics requiring detailed responses"
    ),
    
    "reasoning": LLMPreset(
        temperature=0.3,   # Bassa per ragionamento logico
        max_tokens=3000,   # Spazio per reasoning chain
        stop_sequences=["CONCLUSIONE FINALE:", "---"],
        repetition_penalty=1.05,
        presence_penalty=0.2,
        top_p=0.9,
        description="Deep reasoning and analysis with step-by-step thinking"
    ),
    
    "code_generation": LLMPreset(
        temperature=0.3,
        max_tokens=2048,   # Aumentato per codice più lungo
        stop_sequences=["```\n\n", "# END", "// END"],
        repetition_penalty=1.05,
        presence_penalty=0.2,
        top_p=0.95,
        description="Code generation with low temperature for consistency"
    ),
    
    "creative_writing": LLMPreset(
        temperature=0.9,
        max_tokens=4096,   # Aumentato per contenuti creativi lunghi
        stop_sequences=["THE END", "---END---"],
        repetition_penalty=1.05,
        presence_penalty=0.3,
        top_p=0.98,
        description="Creative writing with high temperature"
    ),
    
    "factual_qa": LLMPreset(
        temperature=0.1,
        max_tokens=512,    # Aumentato da 256
        stop_sequences=["\n\n", "---"],
        repetition_penalty=1.0,
        presence_penalty=0.5,
        top_p=0.85,
        description="Factual Q&A with very low temperature"
    ),
    
    "uncensored": LLMPreset(
        temperature=0.8,
        max_tokens=3000,
        stop_sequences=[],
        repetition_penalty=1.02,
        presence_penalty=0.1,
        top_p=0.95,
        description="Uncensored mode for direct, unfiltered responses"
    ),
}


def get_preset(name: str) -> LLMPreset:
    """Ottieni preset per nome, fallback a 'chat'.
    
    Parameters
    ----------
    name : str
        Nome del preset da recuperare.
    
    Returns
    -------
    LLMPreset
        Il preset richiesto o 'chat' se non trovato.
    
    Examples
    --------
    >>> preset = get_preset("web_synthesis")
    >>> preset.max_tokens
    120
    >>> preset = get_preset("invalid_name")  # Returns 'chat' preset
    >>> preset.max_tokens
    512
    """
    return PRESETS.get(name, PRESETS["chat"])


def to_payload_params(preset: LLMPreset, backend_compatible: bool = True) -> Dict[str, Any]:
    """Converti preset in parametri payload per LLM.
    
    Parameters
    ----------
    preset : LLMPreset
        Il preset da convertire.
    backend_compatible : bool, optional
        Se True, include solo parametri compatibili con backend OpenAI standard.
        Se False, include anche repetition_penalty e presence_penalty.
    
    Returns
    -------
    Dict[str, Any]
        Dizionario di parametri per payload LLM.
    
    Examples
    --------
    >>> preset = get_preset("web_synthesis")
    >>> params = to_payload_params(preset)
    >>> params["temperature"]
    0.2
    >>> params["max_tokens"]
    120
    """
    base_params = {
        "temperature": preset.temperature,
        "max_tokens": preset.max_tokens,
        "top_p": preset.top_p,
    }
    
    # Aggiungi stop sequences solo se non vuote
    if preset.stop_sequences:
        base_params["stop"] = preset.stop_sequences
    
    # Parametri aggiuntivi solo se richiesti e backend supporta
    if not backend_compatible:
        base_params["repetition_penalty"] = preset.repetition_penalty
        base_params["presence_penalty"] = preset.presence_penalty
    
    return base_params


def list_presets() -> List[str]:
    """Restituisce lista di nomi preset disponibili.
    
    Returns
    -------
    List[str]
        Lista dei nomi dei preset.
    
    Examples
    --------
    >>> presets = list_presets()
    >>> "web_synthesis" in presets
    True
    >>> "chat" in presets
    True
    """
    return list(PRESETS.keys())


def get_preset_info(name: str) -> Optional[Dict[str, Any]]:
    """Ottieni informazioni complete su un preset.
    
    Parameters
    ----------
    name : str
        Nome del preset.
    
    Returns
    -------
    Optional[Dict[str, Any]]
        Dizionario con tutte le informazioni del preset, o None se non esiste.
    
    Examples
    --------
    >>> info = get_preset_info("web_synthesis")
    >>> info["description"]
    'Ultra-concise web synthesis (max 50 words, optimized for speed)'
    """
    preset = PRESETS.get(name)
    if preset:
        return asdict(preset)
    return None


# Test rapido
if __name__ == "__main__":
    print("🧪 LLM CONFIG - TEST\n" + "=" * 60)
    
    # Test preset retrieval
    print("\n1. Available presets:")
    for preset_name in list_presets():
        print(f"   - {preset_name}")
    
    # Test web_synthesis preset
    print("\n2. Web Synthesis Preset:")
    ws_preset = get_preset("web_synthesis")
    print(f"   Temperature: {ws_preset.temperature}")
    print(f"   Max Tokens: {ws_preset.max_tokens}")
    print(f"   Stop Sequences: {ws_preset.stop_sequences}")
    print(f"   Description: {ws_preset.description}")
    
    # Test payload conversion
    print("\n3. Payload Parameters (OpenAI compatible):")
    params = to_payload_params(ws_preset, backend_compatible=True)
    for key, value in params.items():
        print(f"   {key}: {value}")
    
    # Test fallback
    print("\n4. Fallback Test (invalid preset):")
    fallback = get_preset("nonexistent_preset")
    print(f"   Got preset: chat (temperature={fallback.temperature})")
    
    print("\n✅ All tests passed!")
