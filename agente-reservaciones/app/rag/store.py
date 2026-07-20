"""
Vector Store (Chroma)
=====================
Wrapper sobre ChromaDB. Se usa en modo "PersistentClient" (embebido, guarda
los datos en disco) para desarrollo local. En producción, esto se puede
cambiar a un cliente HTTP contra un servidor Chroma separado sin tocar
el resto del código del RAG — por eso está aislado en este módulo.
"""

import os

import chromadb
from chromadb.utils import embedding_functions

RUTA_DEFECTO_DB = os.path.join("data", "chroma_local")
NOMBRE_COLECCION_DEFECTO = "conocimiento_negocio"

# Modelo de embeddings local (no requiere llamar a ninguna API paga).
# DefaultEmbeddingFunction usa un modelo ONNX liviano (all-MiniLM-L6-v2)
# que viene con chromadb, sin necesidad de instalar PyTorch completo.
# Se puede cambiar por embeddings de mayor calidad (ej. de OpenAI o
# Voyage) más adelante sin tocar el resto del código del RAG.
_funcion_embeddings = embedding_functions.DefaultEmbeddingFunction()


class VectorStore:
    def __init__(
        self,
        ruta_db: str = RUTA_DEFECTO_DB,
        nombre_coleccion: str = NOMBRE_COLECCION_DEFECTO,
        funcion_embeddings=None,
    ):
        """
        `funcion_embeddings` se puede inyectar para tests (evita depender
        de la descarga del modelo real por red). En uso normal se deja en
        None y se usa el modelo por defecto de Chroma.
        """
        self.cliente = chromadb.PersistentClient(path=ruta_db)
        self.coleccion = self.cliente.get_or_create_collection(
            name=nombre_coleccion,
            embedding_function=funcion_embeddings or _funcion_embeddings,
        )

    def agregar_chunks(self, chunks: list) -> None:
        """
        Agrega una lista de objetos Chunk (ver chunking.py) al vector store.
        El id de cada chunk se genera como "{fuente}::{indice}" para que
        sea determinístico y evitar duplicados si se re-ingesta el mismo
        documento.
        """
        if not chunks:
            return

        ids = [f"{c.fuente}::{c.indice}" for c in chunks]
        documentos = [c.texto for c in chunks]
        metadatos = [{"fuente": c.fuente, "indice": c.indice} for c in chunks]

        self.coleccion.upsert(ids=ids, documents=documentos, metadatas=metadatos)

    def buscar(self, consulta: str, top_k: int = 3) -> list[dict]:
        """
        Busca los `top_k` chunks más relevantes para una consulta.
        Devuelve una lista de dicts con texto, fuente y score de distancia
        (menor distancia = más relevante).
        """
        resultados = self.coleccion.query(query_texts=[consulta], n_results=top_k)

        salida = []
        documentos = resultados.get("documents", [[]])[0]
        metadatos = resultados.get("metadatas", [[]])[0]
        distancias = resultados.get("distances", [[]])[0]

        for doc, meta, dist in zip(documentos, metadatos, distancias):
            salida.append(
                {
                    "texto": doc,
                    "fuente": meta.get("fuente"),
                    "indice": meta.get("indice"),
                    "distancia": dist,
                }
            )

        return salida

    def contar(self) -> int:
        return self.coleccion.count()
