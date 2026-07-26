"""
Evaluación del RAG (recuperación semántica)
===========================================
Mide qué tan bien el buscador trae el chunk correcto para cada pregunta
del dataset (ver casos_rag.py). NO usa el LLM ni gasta cuota: los
embeddings corren locales.

Métricas:
  - recall@1: el chunk correcto salió PRIMERO.
  - recall@3: el chunk correcto salió en el top-3.
  - MRR (mean reciprocal rank): promedio de 1/posición del primer acierto.
    Premia que el acierto esté más arriba (1.0 = siempre primero).

Uso:
    python -m app.eval.evaluar_rag

Para que sea reproducible, ingesta los documentos en un vector store
temporal en cada corrida, en vez de depender del estado de
data/chroma_local.
"""

import re
import tempfile

from app.eval.casos_rag import CASOS
from app.rag.ingest import ingestar
from app.rag.store import VectorStore
from app.rutas import CARPETA_DOCUMENTOS


def _normalizar(texto: str) -> str:
    """
    Minúsculas y espacios colapsados: así el marcador "segundo piso"
    matchea aunque en el documento fuente esté cortado por un salto de
    línea ("segundo\\npiso"). Lo que importa es que el CONTENIDO se haya
    recuperado, no cómo venían acomodados los saltos de línea.
    """
    return re.sub(r"\s+", " ", texto).lower()


def _rango_del_acierto(resultados: list[dict], marcador: str) -> int | None:
    """
    Posición (1-indexada) del primer resultado cuyo texto contiene el
    marcador, o None si ninguno lo contiene.
    """
    marcador = _normalizar(marcador)
    for i, r in enumerate(resultados, start=1):
        if marcador in _normalizar(r.get("texto", "")):
            return i
    return None


def evaluar_recuperacion(store: VectorStore, casos: list[dict], top_k: int = 3) -> dict:
    """
    Corre todos los casos contra el store y devuelve las métricas.

    Función pura (no imprime ni ingesta): recibe el store ya poblado y los
    casos, para poder testearla con un store controlado.

    Returns:
        dict con las métricas globales y el detalle por caso.
    """
    detalle = []
    for caso in casos:
        resultados = store.buscar(caso["pregunta"], top_k=top_k)
        rango = _rango_del_acierto(resultados, caso["marcador"])
        detalle.append(
            {
                **caso,
                "rango": rango,  # None si no lo encontró
                "acierto_top1": rango == 1,
                "acierto_topk": rango is not None,
            }
        )

    total = len(casos)
    top1 = sum(d["acierto_top1"] for d in detalle)
    topk = sum(d["acierto_topk"] for d in detalle)
    mrr = sum(1 / d["rango"] for d in detalle if d["rango"]) / total if total else 0.0

    return {
        "total": total,
        "top_k": top_k,
        "recall_at_1": top1 / total if total else 0.0,
        "recall_at_k": topk / total if total else 0.0,
        "mrr": mrr,
        "detalle": detalle,
    }


def _imprimir_reporte(metricas: dict) -> None:
    top_k = metricas["top_k"]
    print("=" * 68)
    print("EVALUACIÓN DEL RAG — recuperación semántica")
    print("=" * 68)

    print(f"\n{'Pregunta':<44}{'Dif.':<9}{'Rango':<7}{'ok?'}")
    print("-" * 68)
    for d in metricas["detalle"]:
        rango = d["rango"] if d["rango"] else "—"
        ok = "PASA" if d["acierto_topk"] else "FALLA"
        pregunta = d["pregunta"][:42]
        print(f"{pregunta:<44}{d['dificultad']:<9}{str(rango):<7}{ok}")

    print("-" * 68)
    print(f"\nCasos evaluados : {metricas['total']}")
    print(f"recall@1        : {metricas['recall_at_1']:.0%}   (el chunk correcto salió primero)")
    print(f"recall@{top_k}        : {metricas['recall_at_k']:.0%}   (salió en el top-{top_k})")
    print(f"MRR             : {metricas['mrr']:.3f}  (1.0 = siempre primero)")

    # Desglose por dificultad: lo interesante es ver los "difíciles"
    # (paráfrasis sin palabras compartidas), que miden la búsqueda semántica.
    print("\nPor dificultad (recall@{}):".format(top_k))
    for dif in ("facil", "dificil"):
        casos_dif = [d for d in metricas["detalle"] if d["dificultad"] == dif]
        if casos_dif:
            aciertos = sum(d["acierto_topk"] for d in casos_dif)
            print(f"  {dif:<9}: {aciertos}/{len(casos_dif)}  ({aciertos / len(casos_dif):.0%})")


def main() -> None:
    # Vector store temporal, ingestado desde cero para reproducibilidad.
    ruta_tmp = tempfile.mkdtemp(prefix="eval_rag_")
    store = VectorStore(ruta_db=ruta_tmp, nombre_coleccion="eval")

    total_chunks = ingestar(carpeta=str(CARPETA_DOCUMENTOS), store=store)
    print(f"Ingestados {total_chunks} chunks desde {CARPETA_DOCUMENTOS}\n")

    metricas = evaluar_recuperacion(store, CASOS, top_k=3)
    _imprimir_reporte(metricas)


if __name__ == "__main__":
    main()
