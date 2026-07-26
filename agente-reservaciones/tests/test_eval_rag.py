"""
Tests del harness de evaluación del RAG
=======================================
Prueban el cálculo de métricas (rango, recall@1, recall@k, MRR) con un
store controlado, sin embeddings reales ni cuota. Lo que se valida es la
lógica del harness, no la calidad de la búsqueda (eso lo mide la corrida
real contra el vector store).
"""

from app.eval.evaluar_rag import evaluar_recuperacion


class _StoreFalso:
    """
    Store de prueba: para cada pregunta devuelve una lista fija de
    resultados (en orden de relevancia). `respuestas` es un dict
    pregunta -> lista de textos.
    """

    def __init__(self, respuestas):
        self._respuestas = respuestas

    def buscar(self, consulta, top_k=3):
        textos = self._respuestas.get(consulta, [])[:top_k]
        return [{"texto": t} for t in textos]


def test_acierto_en_primera_posicion():
    store = _StoreFalso({"p1": ["contiene el MARCADOR aquí", "otro", "otro"]})
    casos = [{"pregunta": "p1", "marcador": "marcador", "tema": "x", "dificultad": "facil"}]

    m = evaluar_recuperacion(store, casos, top_k=3)

    assert m["detalle"][0]["rango"] == 1
    assert m["recall_at_1"] == 1.0
    assert m["recall_at_k"] == 1.0
    assert m["mrr"] == 1.0


def test_acierto_en_tercera_posicion_no_cuenta_para_recall1():
    store = _StoreFalso({"p1": ["nada", "nada", "acá está el marcador"]})
    casos = [{"pregunta": "p1", "marcador": "marcador", "tema": "x", "dificultad": "facil"}]

    m = evaluar_recuperacion(store, casos, top_k=3)

    assert m["detalle"][0]["rango"] == 3
    assert m["recall_at_1"] == 0.0   # no salió primero
    assert m["recall_at_k"] == 1.0   # pero sí en el top-3
    assert m["mrr"] == 1 / 3


def test_marcador_ausente_es_fallo():
    store = _StoreFalso({"p1": ["nada", "nada", "nada"]})
    casos = [{"pregunta": "p1", "marcador": "marcador", "tema": "x", "dificultad": "facil"}]

    m = evaluar_recuperacion(store, casos, top_k=3)

    assert m["detalle"][0]["rango"] is None
    assert m["recall_at_k"] == 0.0
    assert m["mrr"] == 0.0


def test_comparacion_insensible_a_mayusculas():
    store = _StoreFalso({"p1": ["Aceptamos SINPE móvil"]})
    casos = [{"pregunta": "p1", "marcador": "sinpe", "tema": "pagos", "dificultad": "facil"}]

    m = evaluar_recuperacion(store, casos, top_k=3)

    assert m["detalle"][0]["acierto_top1"] is True


def test_metricas_promedian_varios_casos():
    store = _StoreFalso(
        {
            "p1": ["marcador acá"],          # rango 1
            "p2": ["nada", "marcador acá"],  # rango 2
            "p3": ["nada", "nada", "nada"],  # no aparece
        }
    )
    casos = [
        {"pregunta": "p1", "marcador": "marcador", "tema": "x", "dificultad": "facil"},
        {"pregunta": "p2", "marcador": "marcador", "tema": "x", "dificultad": "facil"},
        {"pregunta": "p3", "marcador": "marcador", "tema": "x", "dificultad": "dificil"},
    ]

    m = evaluar_recuperacion(store, casos, top_k=3)

    assert m["total"] == 3
    assert m["recall_at_1"] == 1 / 3          # solo p1
    assert m["recall_at_k"] == 2 / 3          # p1 y p2
    assert abs(m["mrr"] - (1 + 0.5 + 0) / 3) < 1e-9
