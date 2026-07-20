"""
Tests del RAG
=============
Prueban el pipeline completo (chunking -> guardar -> buscar) de forma
aislada, sin depender del agente ni del servidor MCP, tal como pide la
Fase 1 del backlog.

Se usa un embedding determinístico basado en bag-of-words (no una red
neuronal real) para que los tests corran rápido y sin depender de
descargar un modelo por internet, tanto en local como en CI. La calidad
semántica real se prueba manualmente con el modelo de producción.
"""

import shutil
import tempfile
import uuid

import pytest
from chromadb import EmbeddingFunction

from app.rag.chunking import dividir_en_chunks
from app.rag.store import VectorStore


class EmbeddingBagOfWords(EmbeddingFunction):
    """
    Embedding simple para tests: cada dimensión representa si una palabra
    del vocabulario aparece o no en el texto. No entiende sinónimos ni
    semántica real, pero SÍ detecta correctamente si dos textos comparten
    palabras clave -- suficiente para probar que el pipeline de guardar/
    buscar funciona de punta a punta.
    """

    VOCABULARIO = [
        "horario", "atencion", "sabado", "domingo", "lunes",
        "cancelacion", "cancelar", "penalizacion", "24", "horas",
        "pago", "efectivo", "tarjeta", "sinpe", "transferencia",
        "ubicacion", "parqueo", "parque", "piso",
    ]

    def __call__(self, input):
        vectores = []
        for texto in input:
            texto_normalizado = texto.lower()
            vector = [
                1.0 if palabra in texto_normalizado else 0.0
                for palabra in self.VOCABULARIO
            ]
            # Normalizar a longitud 1 (como hacen los embeddings reales)
            # para que la distancia compare dirección/significado y no
            # "cuántas palabras clave tiene el texto".
            norma = sum(v * v for v in vector) ** 0.5
            if norma > 0:
                vector = [v / norma for v in vector]
            vectores.append(vector)
        return vectores


@pytest.fixture
def store():
    """
    VectorStore aislado en una carpeta temporal única por test. Se usa un
    path distinto en cada test (en vez de borrar/recrear el mismo path)
    porque Chroma cachea conexiones internamente por ruta, y reutilizar
    el mismo path entre tests corrompe el estado.
    """
    ruta = tempfile.mkdtemp(prefix=f"chroma_test_{uuid.uuid4().hex[:8]}_")
    vs = VectorStore(
        ruta_db=ruta,
        nombre_coleccion="test",
        funcion_embeddings=EmbeddingBagOfWords(),
    )
    yield vs
    shutil.rmtree(ruta, ignore_errors=True)


# --- Tests de chunking ---

def test_chunking_texto_vacio_devuelve_lista_vacia():
    assert dividir_en_chunks("", fuente="x.md") == []


def test_chunking_respeta_tamano_maximo_aproximado():
    texto = "palabra " * 200  # ~1600 caracteres
    chunks = dividir_en_chunks(texto, fuente="x.md", max_caracteres=300)
    assert len(chunks) > 1
    for c in chunks:
        # Un poco de margen porque no corta palabras a la mitad
        assert len(c.texto) <= 320


def test_chunking_no_pierde_contenido_relevante():
    texto = "Horario de atención: lunes a viernes. Política de cancelación: 24 horas."
    chunks = dividir_en_chunks(texto, fuente="x.md", max_caracteres=1000)
    assert len(chunks) == 1
    assert "cancelación" in chunks[0].texto


# --- Tests de guardar + buscar (end-to-end del RAG) ---

def test_agregar_y_contar_chunks(store):
    chunks = dividir_en_chunks(
        "El horario de atención es de lunes a sábado.", fuente="doc1.md"
    )
    store.agregar_chunks(chunks)
    assert store.contar() == len(chunks)


def test_busqueda_devuelve_el_chunk_mas_relevante(store):
    store.agregar_chunks(
        dividir_en_chunks(
            "El horario de atención es lunes a sábado.", fuente="horario.md"
        )
    )
    store.agregar_chunks(
        dividir_en_chunks(
            "Aceptamos pago en efectivo, tarjeta y transferencia SINPE.",
            fuente="pagos.md",
        )
    )

    resultados = store.buscar("¿cómo puedo pagar con sinpe?", top_k=1)

    assert len(resultados) == 1
    assert resultados[0]["fuente"] == "pagos.md"


def test_busqueda_en_store_vacio_no_falla(store):
    resultados = store.buscar("cualquier cosa", top_k=3)
    assert resultados == []


def test_ingesta_es_idempotente_no_duplica_chunks(store):
    """Re-ingestar el mismo documento no debe duplicar chunks (mismo id)."""
    chunks = dividir_en_chunks("Contenido de prueba fijo.", fuente="doc.md")
    store.agregar_chunks(chunks)
    store.agregar_chunks(chunks)  # se vuelve a ingestar
    assert store.contar() == len(chunks)
