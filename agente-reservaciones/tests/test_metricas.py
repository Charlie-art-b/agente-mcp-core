"""
Tests del cálculo de métricas (Fase 6)
======================================
Prueban `calcular_metricas` con filas controladas en SQLite en memoria,
sin Postgres ni cuota.
"""

import pytest

from app.db.models import InteraccionLog
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas
from app.logging.metricas import calcular_metricas


@pytest.fixture
def sesion():
    engine = crear_engine("sqlite:///:memory:")
    crear_tablas(engine)
    s = crear_fabrica_sesiones(engine)()
    yield s
    s.close()


def _agregar(sesion, **campos):
    base = {
        "mensaje_usuario": "hola",
        "tool_llamada": None,
        "tokens_input": 100,
        "tokens_output": 20,
        "costo_usd": 0.0001,
        "latencia_ms": 5000,
    }
    base.update(campos)
    sesion.add(InteraccionLog(**base))
    sesion.commit()


def test_base_vacia_devuelve_ceros(sesion):
    m = calcular_metricas(sesion)

    assert m["total_interacciones"] == 0
    assert m["costo_total_usd"] == 0.0
    assert m["uso_por_tool"] == {}
    assert m["ultimas"] == []


def test_cuenta_totales_costo_y_tokens(sesion):
    _agregar(sesion, costo_usd=0.0002, tokens_input=100, tokens_output=50)
    _agregar(sesion, costo_usd=0.0003, tokens_input=200, tokens_output=100)

    m = calcular_metricas(sesion)

    assert m["total_interacciones"] == 2
    assert abs(m["costo_total_usd"] - 0.0005) < 1e-9
    assert m["tokens_total"] == 450  # 150 + 300


def test_latencia_es_promedio(sesion):
    _agregar(sesion, latencia_ms=4000)
    _agregar(sesion, latencia_ms=6000)

    assert calcular_metricas(sesion)["latencia_promedio_ms"] == 5000


def test_cuenta_uso_por_tool_separando_comas(sesion):
    _agregar(sesion, tool_llamada="consultar_disponibilidad")
    _agregar(sesion, tool_llamada="consultar_disponibilidad,crear_reservacion")
    _agregar(sesion, tool_llamada=None)  # sin tool

    m = calcular_metricas(sesion)

    assert m["uso_por_tool"] == {"consultar_disponibilidad": 2, "crear_reservacion": 1}
    assert m["interacciones_sin_tool"] == 1


def test_uso_por_tool_viene_ordenado_de_mayor_a_menor(sesion):
    _agregar(sesion, tool_llamada="escalar_caso")
    _agregar(sesion, tool_llamada="buscar_conocimiento")
    _agregar(sesion, tool_llamada="buscar_conocimiento")

    orden = list(calcular_metricas(sesion)["uso_por_tool"].keys())
    assert orden[0] == "buscar_conocimiento"  # 2 usos va primero


def test_ultimas_trae_las_mas_recientes_primero(sesion):
    _agregar(sesion, mensaje_usuario="primera")
    _agregar(sesion, mensaje_usuario="segunda")

    ultimas = calcular_metricas(sesion)["ultimas"]
    assert ultimas[0]["mensaje_usuario"] == "segunda"
