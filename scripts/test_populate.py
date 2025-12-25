#!/usr/bin/env python3
"""
tests/test_populate.py

Test di integrazione leggero per lo script:
    scripts/populate_knowledge_base.py

Obiettivi:
- Verificare che lo script importi correttamente.
- Verificare che chiami almeno una volta `add_fact` con la nuova firma
  (content, source=None, tags=None).
- Non toccare il ChromaDB reale: usiamo una finta `add_fact`.
"""

import asyncio


def test_populate_knowledge_base_calls_add_fact():
    """
    Importa lo script, sostituisce add_fact con una finta funzione
    che registra le chiamate e verifica che venga invocata almeno una volta.
    """
    import scripts.populate_knowledge_base as kb  # type: ignore

    calls = []

    def fake_add_fact(content, source=None, tags=None):
        calls.append(
            {
                "content": content,
                "source": source,
                "tags": tags,
            }
        )

    # Backup dell'originale (se esiste)
    original_add_fact = getattr(kb, "add_fact", None)

    # Patch
    kb.add_fact = fake_add_fact  # type: ignore[attr-defined]

    try:
        # Deve esistere una funzione main async nello script
        main_fn = getattr(kb, "main", None)
        assert main_fn is not None, "scripts.populate_knowledge_base.main non trovato"

        # Eseguiamo lo script in modalità test (nessuna scrittura su Chroma reale)
        asyncio.run(main_fn())

    finally:
        # Ripristina add_fact originale se c'era
        if original_add_fact is not None:
            kb.add_fact = original_add_fact  # type: ignore[attr-defined]

    # Assert: almeno una chiamata registrata
    assert len(calls) > 0, "populate_knowledge_base non ha mai chiamato add_fact"

    # Sanity-check minimo su una delle chiamate
    first = calls[0]
    assert "content" in first, "fake_add_fact ha ricevuto argomenti inattesi"
    assert isinstance(first["content"], str) and first["content"].strip(), "content vuoto o non stringa"


if __name__ == "__main__":
    # Esecuzione manuale: utile se lo lanci con `python tests/test_populate.py`
    test_populate_knowledge_base_calls_add_fact()
    print("OK - test_populate_knowledge_base_calls_add_fact passato.")
