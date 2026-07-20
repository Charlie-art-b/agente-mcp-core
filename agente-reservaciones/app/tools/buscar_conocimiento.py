"""
Tool: buscar_conocimiento
==========================
Esta función es el "cuerpo" de la tool que, en la Fase 3, se va a exponer
a través del servidor MCP. Se construye y se prueba aquí, aislada, para
confirmar que el RAG funciona bien antes de conectarla a nada más.
"""

from app.rag.store import VectorStore

_store: VectorStore | None = None


def _get_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store


def buscar_conocimiento(consulta: str, top_k: int = 3) -> dict:
    """
    Busca en la base de conocimiento del negocio la información más
    relevante para responder una consulta del usuario.

    Args:
        consulta: la pregunta o texto del usuario.
        top_k: cuántos resultados devolver.

    Returns:
        dict con la lista de resultados encontrados, cada uno con su
        texto, fuente del documento y qué tan relevante es (distancia).
    """
    store = _get_store()

    if store.contar() == 0:
        return {
            "resultados": [],
            "advertencia": "La base de conocimiento está vacía. Corré "
            "'python -m app.rag.ingest' primero.",
        }

    resultados = store.buscar(consulta, top_k=top_k)
    return {"resultados": resultados}
