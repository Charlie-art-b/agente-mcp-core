"""
Tests del harness de evaluación end-to-end
==========================================
Prueban la lógica del harness (latencia, suma de tokens, costo,
correctitud por marcadores) con un agente falso y la verificación de base
mockeada. Sin Gemini, sin Postgres, sin cuota.
"""

import pytest

from app.eval import evaluar_e2e as mod
from app.eval.evaluar_e2e import evaluar_conversacion, evaluar_e2e


class _AgenteFalso:
    """
    Devuelve respuestas predefinidas turno a turno y reporta un uso de
    tokens fijo por turno, imitando a AgenteReservaciones.
    """

    def __init__(self, respuestas, uso_por_turno=None):
        self._respuestas = list(respuestas)
        self._usos = list(uso_por_turno or [{"tokens_entrada": 100, "tokens_salida": 20, "tokens_total": 120}] * len(respuestas))
        self._i = 0
        self.ultimo_uso = {"tokens_entrada": 0, "tokens_salida": 0, "tokens_total": 0}

    def consultar(self, turno):
        respuesta = self._respuestas[self._i]
        self.ultimo_uso = self._usos[self._i]
        self._i += 1
        return respuesta


@pytest.fixture(autouse=True)
def _sin_base(monkeypatch):
    """Por defecto, la verificación de base 'pasa'. Cada test la ajusta si hace falta."""
    monkeypatch.setattr(mod, "_efecto_db_ok", lambda efecto: True)


def test_conversacion_correcta_con_marcador():
    agente = _AgenteFalso(["La cancelación es hasta 24 horas antes."])
    caso = {
        "nombre": "conocimiento",
        "turnos": ["¿política?"],
        "marcadores": ["24 horas"],
        "efecto_db": None,
    }

    r = evaluar_conversacion(agente, caso)

    assert r["correcto"] is True
    assert r["marcadores_ok"] is True
    assert r["latencia_s"] >= 0
    assert r["tokens"]["total"] == 120


def test_marcador_ausente_es_fallo():
    agente = _AgenteFalso(["No tengo esa información."])
    caso = {
        "nombre": "x",
        "turnos": ["¿política?"],
        "marcadores": ["24 horas"],
        "efecto_db": None,
    }

    r = evaluar_conversacion(agente, caso)

    assert r["marcadores_ok"] is False
    assert r["correcto"] is False


def test_suma_tokens_y_toma_la_ultima_respuesta_en_multi_turno():
    agente = _AgenteFalso(
        ["Tenemos las 09:00 y 10:00.", "Listo, reservado."],
        uso_por_turno=[
            {"tokens_entrada": 200, "tokens_salida": 30, "tokens_total": 230},
            {"tokens_entrada": 300, "tokens_salida": 40, "tokens_total": 340},
        ],
    )
    caso = {"nombre": "reserva", "turnos": ["¿campo?", "agendame"], "marcadores": [], "efecto_db": None}

    r = evaluar_conversacion(agente, caso)

    assert r["turnos"] == 2
    assert r["tokens"]["total"] == 570
    assert r["respuesta_final"] == "Listo, reservado."


def test_verificacion_de_base_puede_hacer_fallar_el_caso(monkeypatch):
    """Aunque la respuesta esté bien, si el cambio no quedó en la base, falla."""
    monkeypatch.setattr(mod, "_efecto_db_ok", lambda efecto: False)
    agente = _AgenteFalso(["Listo, reservado."])
    caso = {
        "nombre": "reserva",
        "turnos": ["agendame"],
        "marcadores": [],
        "efecto_db": {"tipo": "reservacion", "telefono": "x"},
    }

    r = evaluar_conversacion(agente, caso)

    assert r["db_ok"] is False
    assert r["correcto"] is False


def test_costo_se_calcula_desde_los_tokens():
    agente = _AgenteFalso(
        ["ok"],
        uso_por_turno=[{"tokens_entrada": 1_000_000, "tokens_salida": 1_000_000, "tokens_total": 2_000_000}],
    )
    caso = {"nombre": "x", "turnos": ["hola"], "marcadores": [], "efecto_db": None}

    r = evaluar_conversacion(agente, caso)

    # 1M entrada * precio_in + 1M salida * precio_out
    esperado = mod.PRECIO_ENTRADA_POR_1M + mod.PRECIO_SALIDA_POR_1M
    assert abs(r["costo_usd"] - esperado) < 1e-9


def test_evaluar_e2e_agrega_las_metricas():
    casos = [
        {"nombre": "a", "turnos": ["p"], "marcadores": ["si"], "efecto_db": None},
        {"nombre": "b", "turnos": ["p"], "marcadores": ["no aparece"], "efecto_db": None},
    ]
    respuestas = {"a": ["si señor"], "b": ["cualquier cosa"]}
    # Fábrica: un agente fresco por caso, con la respuesta que le toca.
    orden = iter(["a", "b"])

    def crear_agente():
        nombre = next(orden)
        return _AgenteFalso(respuestas[nombre])

    m = evaluar_e2e(crear_agente, casos)

    assert m["total"] == 2
    assert m["correctos"] == 1        # solo "a" tiene su marcador
    assert m["accuracy"] == 0.5
    assert m["tokens_total"] == 240   # 120 por caso
