"""
Evaluación end-to-end (correctitud + latencia + costo)
======================================================
Corre conversaciones completas contra el agente real y mide tres cosas:

  - Correctitud: ¿la respuesta final tiene los marcadores esperados Y el
    cambio esperado quedó en la base? (ver casos_e2e.py)
  - Latencia: cuánto tardó cada conversación, de punta a punta.
  - Costo: los tokens que reportó Gemini, y un costo estimado a partir de
    ellos.

Es la evaluación más cara en cuota: cada turno son 1-2 llamadas a Gemini,
y las conversaciones tienen varios turnos. Por eso espacia los turnos para
respetar el límite de la capa gratuita. En una capa paga se baja la pausa.

Uso (requiere Postgres corriendo):
    python -m app.eval.evaluar_e2e

Ojo: RESETEA la base (borra y vuelve a sembrar) para que la corrida sea
reproducible. No la corras sobre datos que quieras conservar.
"""

import time

from app.db.models import Base, Cliente, Reservacion, TicketEscalado
from app.db.seed import sembrar_datos_ejemplo
from app.db.session import obtener_engine_defecto, obtener_sesion
from app.eval.casos_e2e import CASOS
from app.precios import (
    PRECIO_ENTRADA_POR_1M,
    PRECIO_SALIDA_POR_1M,
    costo_de_tokens,
)

# Pausa entre turnos para no pasar el límite de ~5 llamadas/min de la capa
# gratuita (un turno con tool son 2 llamadas). En capa paga, poné 0.
PAUSA_ENTRE_TURNOS_SEGUNDOS = 22.0


def reiniciar_base() -> None:
    """Deja la base en un estado limpio y conocido: borra todo y siembra."""
    engine = obtener_engine_defecto()
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    sembrar_datos_ejemplo()


def _normalizar(texto: str) -> str:
    import re

    return re.sub(r"\s+", " ", texto).lower()


def _marcadores_presentes(respuesta: str, marcadores: list[str]) -> bool:
    r = _normalizar(respuesta)
    return all(_normalizar(m) in r for m in marcadores)


def _efecto_db_ok(efecto: dict | None) -> bool:
    """Verifica en Postgres que el cambio esperado quedó registrado."""
    if efecto is None:
        return True

    sesion = obtener_sesion()
    try:
        tel = efecto["telefono"]
        if efecto["tipo"] == "reservacion":
            n = (
                sesion.query(Reservacion)
                .join(Cliente)
                .filter(Cliente.telefono == tel)
                .count()
            )
        elif efecto["tipo"] == "ticket":
            n = (
                sesion.query(TicketEscalado)
                .join(Cliente)
                .filter(Cliente.telefono == tel)
                .count()
            )
        else:
            return False
        return n > 0
    finally:
        sesion.close()


def evaluar_conversacion(agente, caso: dict, pausa: float = 0.0) -> dict:
    """
    Corre una conversación completa y mide latencia, tokens y correctitud.

    `agente` debe ser una instancia fresca (historial vacío). `pausa` es la
    espera entre turnos para respetar el rate limit; en tests va en 0.
    """
    latencia_total = 0.0
    tokens = {"entrada": 0, "salida": 0, "total": 0}
    respuesta_final = ""

    for i, turno in enumerate(caso["turnos"]):
        if i > 0 and pausa:
            time.sleep(pausa)

        inicio = time.monotonic()
        respuesta_final = agente.consultar(turno)
        latencia_total += time.monotonic() - inicio

        tokens["entrada"] += agente.ultimo_uso["tokens_entrada"]
        tokens["salida"] += agente.ultimo_uso["tokens_salida"]
        tokens["total"] += agente.ultimo_uso["tokens_total"]

    marcadores_ok = _marcadores_presentes(respuesta_final, caso["marcadores"])
    db_ok = _efecto_db_ok(caso["efecto_db"])

    costo = costo_de_tokens(tokens["entrada"], tokens["salida"])

    return {
        "nombre": caso["nombre"],
        "turnos": len(caso["turnos"]),
        "correcto": marcadores_ok and db_ok,
        "marcadores_ok": marcadores_ok,
        "db_ok": db_ok,
        "latencia_s": latencia_total,
        "tokens": tokens,
        "costo_usd": costo,
        "respuesta_final": respuesta_final,
    }


def evaluar_e2e(crear_agente, casos: list[dict], pausa: float = 0.0) -> dict:
    """
    Corre todos los casos, cada uno con un agente fresco, y agrega métricas.

    `crear_agente` es una fábrica (callable sin argumentos que devuelve un
    agente nuevo), para poder inyectar un doble en los tests.
    """
    detalle = []
    for i, caso in enumerate(casos):
        # Espaciar también ENTRE casos (no solo entre turnos) para respetar
        # el límite por minuto de la capa gratuita.
        if i > 0 and pausa:
            time.sleep(pausa)
        detalle.append(evaluar_conversacion(crear_agente(), caso, pausa=pausa))

    total = len(detalle)
    correctos = sum(d["correcto"] for d in detalle)
    tokens_total = sum(d["tokens"]["total"] for d in detalle)
    costo_total = sum(d["costo_usd"] for d in detalle)
    lat_prom = sum(d["latencia_s"] for d in detalle) / total if total else 0.0

    return {
        "total": total,
        "correctos": correctos,
        "accuracy": correctos / total if total else 0.0,
        "latencia_promedio_s": lat_prom,
        "tokens_total": tokens_total,
        "costo_total_usd": costo_total,
        "detalle": detalle,
    }


def _imprimir_reporte(metricas: dict) -> None:
    print("=" * 74)
    print("EVALUACIÓN END-TO-END — correctitud · latencia · costo")
    print("=" * 74)

    print(f"\n{'Caso':<36}{'ok?':<7}{'Latencia':<11}{'Tokens':<9}{'Costo'}")
    print("-" * 74)
    for d in metricas["detalle"]:
        ok = "PASA" if d["correcto"] else "FALLA"
        print(
            f"{d['nombre'][:34]:<36}{ok:<7}"
            f"{d['latencia_s']:>6.1f}s    {d['tokens']['total']:>6}   "
            f"${d['costo_usd']:.5f}"
        )

    print("-" * 74)
    print(f"\nCasos            : {metricas['total']}")
    print(f"Correctos        : {metricas['correctos']}/{metricas['total']}  "
          f"({metricas['accuracy']:.0%})")
    print(f"Latencia promedio: {metricas['latencia_promedio_s']:.1f}s por conversación")
    print(f"Tokens totales   : {metricas['tokens_total']:,}")
    print(f"Costo estimado   : ${metricas['costo_total_usd']:.5f} "
          f"(a ${PRECIO_ENTRADA_POR_1M}/{PRECIO_SALIDA_POR_1M} por 1M in/out — verificá el precio actual)")

    fallos = [d for d in metricas["detalle"] if not d["correcto"]]
    if fallos:
        print("\nFallos:")
        for d in fallos:
            motivo = []
            if not d["marcadores_ok"]:
                motivo.append("faltan marcadores en la respuesta")
            if not d["db_ok"]:
                motivo.append("el cambio no quedó en la base")
            print(f"  {d['nombre']}: {'; '.join(motivo)}")


def main() -> None:
    from app.agente.agent import AgenteReservaciones

    print("Reseteando y sembrando la base...\n")
    reiniciar_base()

    metricas = evaluar_e2e(
        AgenteReservaciones, CASOS, pausa=PAUSA_ENTRE_TURNOS_SEGUNDOS
    )
    _imprimir_reporte(metricas)


if __name__ == "__main__":
    main()
