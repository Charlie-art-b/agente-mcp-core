"""
Ingesta de documentos
=====================
Lee todos los archivos .md y .txt de `data/documents/`, los divide en
chunks, y los guarda en el vector store. Se corre una vez al inicio y
cada vez que se actualiza la base de conocimiento.

Uso:
    python -m app.rag.ingest
"""

import os

from app.rag.chunking import dividir_en_chunks
from app.rag.store import VectorStore

CARPETA_DOCUMENTOS = os.path.join("data", "documents")
EXTENSIONES_VALIDAS = (".md", ".txt")


def cargar_documentos(carpeta: str = CARPETA_DOCUMENTOS) -> dict[str, str]:
    """Devuelve un dict {nombre_archivo: contenido} de todos los documentos."""
    documentos = {}
    if not os.path.isdir(carpeta):
        return documentos

    for nombre_archivo in os.listdir(carpeta):
        if nombre_archivo.endswith(EXTENSIONES_VALIDAS):
            ruta = os.path.join(carpeta, nombre_archivo)
            with open(ruta, "r", encoding="utf-8") as f:
                documentos[nombre_archivo] = f.read()

    return documentos


def ingestar(carpeta: str = CARPETA_DOCUMENTOS, store: VectorStore | None = None) -> int:
    """
    Ingesta todos los documentos de la carpeta al vector store.
    Devuelve la cantidad total de chunks ingestados.
    """
    store = store or VectorStore()
    documentos = cargar_documentos(carpeta)

    total_chunks = 0
    for nombre_archivo, contenido in documentos.items():
        chunks = dividir_en_chunks(contenido, fuente=nombre_archivo)
        store.agregar_chunks(chunks)
        total_chunks += len(chunks)
        print(f"  ✓ {nombre_archivo}: {len(chunks)} chunks")

    return total_chunks


if __name__ == "__main__":
    print("Ingestando documentos...")
    total = ingestar()
    print(f"\nListo. {total} chunks ingestados en total.")
