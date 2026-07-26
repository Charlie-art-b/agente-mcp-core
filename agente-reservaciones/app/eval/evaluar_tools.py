"""
Evaluación de selección de tools
================================
Mide si el agente elige la tool correcta para cada mensaje del dataset
(ver casos_tools.py).

A diferencia de la evaluación del RAG, esta SÍ llama a Gemini: una llamada
por caso. Solo mira la PRIMERA decisión del modelo (qué tool pide), sin
ejecutar la tool ni correr la conversación entera — así el costo es mínimo.

Métricas:
  - accuracy global: aciertos / total.
  - accuracy por categoría: dónde el agente rutea bien y dónde se confunde.
  - matriz de confusión chica: cuando falla, qué eligió en vez de lo correcto.

Uso:
    python -m app.eval.evaluar_tools

Ojo: gasta cuota de Gemini (una llamada por caso). El dataset es chico a
propósito.
"""

import time

from google.genai import errors as genai_errors
from google.genai import types

from app.agente.agent import AgenteReservaciones
from app.eval.casos_tools import CASOS

# La capa gratuita de Gemini limita a ~5 llamadas por minuto (por modelo).
# Espaciar las llamadas ~13s mantiene el ritmo por debajo de ese tope. En
# una capa paga se puede bajar a 0 y el harness vuela.
INTERVALO_MINIMO_SEGUNDOS = 13.0
REINTENTOS_POR_LIMITE = 3


def crear_seleccionador(
    agente: AgenteReservaciones,
    intervalo_minimo: float = INTERVALO_MINIMO_SEGUNDOS,
):
    """
    Devuelve una función `mensaje -> [tools que el modelo pidió]`.

    Hace UNA sola llamada a Gemini con el mensaje y las tools declaradas
    del agente (mismas declaraciones y mismo prompt de sistema que usa en
    producción), y devuelve los nombres de las tools que pidió — lista
    vacía si respondió sin usar ninguna.

    Respeta el límite de llamadas por minuto de la capa gratuita: espera al
    menos `intervalo_minimo` segundos entre una llamada y la siguiente, y si
    igual pega un 429 (rate limit) o un 503 (sobrecarga transitoria), espera
    y reintenta.
    """
    config = types.GenerateContentConfig(
        tools=agente._tools,
        system_instruction=agente._prompt_sistema(),
        safety_settings=agente.safety_settings,
    )
    estado = {"ultimo_llamado": 0.0}

    def _esperar_turno():
        falta = intervalo_minimo - (time.monotonic() - estado["ultimo_llamado"])
        if falta > 0:
            time.sleep(falta)
        estado["ultimo_llamado"] = time.monotonic()

    def seleccionar(mensaje: str) -> list[str]:
        contenido = [types.Content(role="user", parts=[types.Part(text=mensaje)])]
        for intento in range(REINTENTOS_POR_LIMITE):
            _esperar_turno()
            try:
                respuesta = agente.client.models.generate_content(
                    model=agente.modelo, contents=contenido, config=config
                )
                if respuesta.function_calls:
                    return [fc.name for fc in respuesta.function_calls]
                return []
            except (genai_errors.ClientError, genai_errors.ServerError):
                # 429 (cuota por minuto) o 503 (sobrecarga): esperar y reintentar.
                if intento == REINTENTOS_POR_LIMITE - 1:
                    raise
                time.sleep(20)
        return []

    return seleccionar


def evaluar_seleccion(seleccionador, casos: list[dict]) -> dict:
    """
    Corre todos los casos y devuelve las métricas.

    Función pura respecto del modelo: recibe `seleccionador` (una función
    mensaje -> lista de tools) para poder testearla con un doble, sin
    llamar a Gemini de verdad.
    """
    detalle = []
    for caso in casos:
        seleccionadas = seleccionador(caso["mensaje"])
        esperada = caso["tool_esperada"]

        if esperada is None:
            acierto = seleccionadas == []
        else:
            acierto = esperada in seleccionadas

        detalle.append({**caso, "seleccionadas": seleccionadas, "acierto": acierto})

    total = len(casos)
    aciertos = sum(d["acierto"] for d in detalle)

    # Accuracy por categoría.
    categorias = {}
    for d in detalle:
        cat = categorias.setdefault(d["categoria"], {"aciertos": 0, "total": 0})
        cat["total"] += 1
        cat["aciertos"] += int(d["acierto"])

    return {
        "total": total,
        "aciertos": aciertos,
        "accuracy": aciertos / total if total else 0.0,
        "por_categoria": categorias,
        "detalle": detalle,
    }


def _fmt_tools(tools: list[str]) -> str:
    return ", ".join(tools) if tools else "(ninguna)"


def _imprimir_reporte(metricas: dict) -> None:
    print("=" * 72)
    print("EVALUACIÓN DE SELECCIÓN DE TOOLS")
    print("=" * 72)

    print(f"\n{'Mensaje':<42}{'Esperada':<16}{'ok?'}")
    print("-" * 72)
    for d in metricas["detalle"]:
        esperada = d["tool_esperada"] or "(ninguna)"
        ok = "PASA" if d["acierto"] else "FALLA"
        print(f"{d['mensaje'][:40]:<42}{esperada[:14]:<16}{ok}")

    print("-" * 72)
    print(f"\nCasos evaluados : {metricas['total']}")
    print(f"Accuracy global : {metricas['accuracy']:.0%}  ({metricas['aciertos']}/{metricas['total']})")

    print("\nPor categoría:")
    for cat, v in metricas["por_categoria"].items():
        print(f"  {cat:<16}: {v['aciertos']}/{v['total']}  ({v['aciertos'] / v['total']:.0%})")

    fallos = [d for d in metricas["detalle"] if not d["acierto"]]
    if fallos:
        print("\nDónde se confundió:")
        for d in fallos:
            esperada = d["tool_esperada"] or "(ninguna)"
            print(f"  {d['mensaje'][:44]!r}")
            print(f"      esperaba: {esperada}   eligió: {_fmt_tools(d['seleccionadas'])}")


def main() -> None:
    agente = AgenteReservaciones()
    seleccionador = crear_seleccionador(agente)
    metricas = evaluar_seleccion(seleccionador, CASOS)
    _imprimir_reporte(metricas)


if __name__ == "__main__":
    main()
