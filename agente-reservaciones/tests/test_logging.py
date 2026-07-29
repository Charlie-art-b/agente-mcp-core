"""
Tests del logging de interacciones (Fase 6)
===========================================
Prueban que `registrar_interaccion` guarda bien en la tabla
interacciones_log, usando SQLite en memoria — sin Postgres, sin cuota.
"""

import pytest

from app.db.models import InteraccionLog
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas
from app.logging.registro import registrar_interaccion
from app.precios import costo_de_tokens


@pytest.fixture
def sesion():
    engine = crear_engine("sqlite:///:memory:")
    crear_tablas(engine)
    s = crear_fabrica_sesiones(engine)()
    yield s
    s.close()


def _registro(**cambios):
    base = {
        "mensaje_usuario": "¿Tenés campo mañana para un corte?",
        "tools": [
            {
                "nombre": "consultar_disponibilidad",
                "input": {"fecha": "2026-08-01", "servicio": "corte"},
                "output": {"total": 2, "disponibles": [{"horario_id": 1}]},
            }
        ],
        "respuesta_agente": "Tenemos las 09:00 y 10:00.",
        "tokens_entrada": 1500,
        "tokens_salida": 200,
        "tokens_total": 1700,
        "latencia_ms": 8300,
    }
    base.update(cambios)
    return base


def test_guarda_la_interaccion_con_sus_datos(sesion):
    id_log = registrar_interaccion(_registro(), sesion=sesion)

    log = sesion.get(InteraccionLog, id_log)
    assert log is not None
    assert log.mensaje_usuario.startswith("¿Tenés campo")
    assert log.tool_llamada == "consultar_disponibilidad"
    assert log.tokens_input == 1500
    assert log.tokens_output == 200
    assert log.latencia_ms == 8300


def test_guarda_input_y_output_de_las_tools(sesion):
    id_log = registrar_interaccion(_registro(), sesion=sesion)

    log = sesion.get(InteraccionLog, id_log)
    assert log.tool_input[0]["fecha"] == "2026-08-01"
    assert log.tool_output[0]["total"] == 2


def test_calcula_el_costo_desde_los_tokens(sesion):
    id_log = registrar_interaccion(_registro(), sesion=sesion)

    log = sesion.get(InteraccionLog, id_log)
    esperado = costo_de_tokens(1500, 200)
    assert abs(float(log.costo_usd) - esperado) < 1e-9


def test_turno_sin_tools_deja_los_campos_de_tool_vacios(sesion):
    id_log = registrar_interaccion(
        _registro(tools=[], respuesta_agente="¡Hola! ¿En qué te ayudo?"), sesion=sesion
    )

    log = sesion.get(InteraccionLog, id_log)
    assert log.tool_llamada is None
    assert log.tool_input is None
    assert log.tool_output is None


def test_varias_tools_se_guardan_juntas(sesion):
    reg = _registro(
        tools=[
            {"nombre": "consultar_disponibilidad", "input": {}, "output": {}},
            {"nombre": "crear_reservacion", "input": {"horario_id": 1}, "output": {"creada": True}},
        ]
    )
    id_log = registrar_interaccion(reg, sesion=sesion)

    log = sesion.get(InteraccionLog, id_log)
    assert log.tool_llamada == "consultar_disponibilidad,crear_reservacion"
    assert len(log.tool_output) == 2


def test_registro_vacio_no_guarda_nada(sesion):
    assert registrar_interaccion({}, sesion=sesion) is None
    assert sesion.query(InteraccionLog).count() == 0
