"""
Tests del agente (Fase 4)
=========================
Prueban la lógica del agente SIN llamar a Gemini ni levantar el servidor
MCP: tanto el cliente de Gemini como el ClienteMCP se reemplazan por dobles
de prueba. Así los tests corren rápido, sin red, sin cuota y sin depender
de que Postgres esté arriba.

Lo que se valida es el bucle del agente: detectar el patrón [TOOL: ...],
parsear los argumentos, ejecutar la tool, y redactar la respuesta final.
La conexión real con Gemini y con las tools ya está cubierta por los
scripts de scripts/ (que sí usan las APIs reales) y por los tests de MCP.
"""

import pytest

from app.agente.agent import AgenteReservaciones


# --- Dobles de prueba ---


class _RespuestaGemini:
    def __init__(self, texto: str):
        self.text = texto


class _ClienteGeminiFalso:
    """Devuelve textos predefinidos, uno por cada llamada a generate_content."""

    def __init__(self, textos):
        self._textos = list(textos)
        self.llamadas = []
        self.models = self

    def generate_content(self, **kwargs):
        self.llamadas.append(kwargs)
        return _RespuestaGemini(self._textos.pop(0))


class _ClienteMCPFalso:
    """Registra las tools ejecutadas y devuelve un resultado fijo."""

    ejecutadas = []
    resultado = {
        "total": 2,
        "disponibles": [
            {"horario_id": 1, "hora_inicio": "09:00", "servicio": "Corte de cabello"},
            {"horario_id": 2, "hora_inicio": "10:00", "servicio": "Corte de cabello"},
        ],
    }

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def ejecutar_tool(self, nombre_tool, **kwargs):
        _ClienteMCPFalso.ejecutadas.append((nombre_tool, kwargs))
        return _ClienteMCPFalso.resultado


@pytest.fixture
def agente(monkeypatch):
    """Agente con el cliente de Gemini y el ClienteMCP reemplazados por dobles."""
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr("app.agente.agent.ClienteMCP", _ClienteMCPFalso)
    _ClienteMCPFalso.ejecutadas = []

    a = AgenteReservaciones()

    def usar_textos(*textos):
        a.client = _ClienteGeminiFalso(textos)
        return a

    a.usar_textos = usar_textos
    return a


# --- El parser de argumentos ---


def test_parsea_string_entero_y_booleano(agente):
    args = agente._parsear_argumentos('nombre="Ana Pérez", horario_id=5, ok=true')

    assert args == {"nombre": "Ana Pérez", "horario_id": 5, "ok": True}


def test_parsea_floats_y_negativos(agente):
    args = agente._parsear_argumentos("precio=8000.50, saldo=-3, ajuste=-1.5")

    assert args == {"precio": 8000.50, "saldo": -3, "ajuste": -1.5}


def test_ignora_valores_que_no_reconoce(agente):
    """Mejor omitir un valor raro que pasarle basura a la tool."""
    args = agente._parsear_argumentos('fecha="2026-08-01", raro=<algo>')

    assert args == {"fecha": "2026-08-01"}


# --- El bucle de tool-calling ---


@pytest.mark.asyncio
async def test_ejecuta_la_tool_que_gemini_pide(agente):
    a = agente.usar_textos(
        '[TOOL: consultar_disponibilidad] (fecha="2026-07-25", servicio="corte")',
        "Tenemos las 09:00 y las 10:00 disponibles. ¿Cuál preferís?",
    )

    respuesta = await a.responder("¿Tenés campo mañana para corte?")

    # Se ejecutó la tool correcta con los argumentos parseados.
    assert _ClienteMCPFalso.ejecutadas == [
        ("consultar_disponibilidad", {"fecha": "2026-07-25", "servicio": "corte"})
    ]
    # La respuesta final es la segunda redacción de Gemini, sin el [TOOL].
    assert "09:00" in respuesta
    assert "[TOOL" not in respuesta


@pytest.mark.asyncio
async def test_sin_tool_devuelve_el_texto_directo(agente):
    """Si Gemini no pide ninguna tool, no se llama a MCP ni se redacta de nuevo."""
    a = agente.usar_textos("¡Hola! ¿En qué te puedo ayudar?")

    respuesta = await a.responder("Hola")

    assert respuesta == "¡Hola! ¿En qué te puedo ayudar?"
    assert _ClienteMCPFalso.ejecutadas == []
    assert len(a.client.llamadas) == 1  # una sola llamada, sin segunda redacción


@pytest.mark.asyncio
async def test_guarda_el_resultado_en_el_contexto_operativo(agente):
    """El resultado crudo queda disponible para turnos futuros (horario_id, etc.)."""
    a = agente.usar_textos(
        '[TOOL: consultar_disponibilidad] (fecha="2026-07-25")',
        "Hay dos horarios libres.",
    )

    await a.responder("¿Qué hay mañana?")

    assert "consultar_disponibilidad" in a.contexto_tools
    guardado = a.contexto_tools["consultar_disponibilidad"]["resultado"]
    assert guardado["disponibles"][0]["horario_id"] == 1


@pytest.mark.asyncio
async def test_una_tool_que_falla_no_tumba_el_turno(agente, monkeypatch):
    """Si la tool lanza, el error se comunica en la respuesta, no explota."""

    async def explota(self, nombre_tool, **kwargs):
        raise RuntimeError("servidor caído")

    monkeypatch.setattr(_ClienteMCPFalso, "ejecutar_tool", explota)

    a = agente.usar_textos(
        '[TOOL: consultar_disponibilidad] (fecha="2026-07-25")',
        "Disculpá, no pude consultar la disponibilidad en este momento.",
    )

    respuesta = await a.responder("¿Hay campo mañana?")

    # El turno terminó con una respuesta redactada, sin propagar la excepción.
    assert isinstance(respuesta, str)
    assert "[TOOL" not in respuesta


def test_cerrar_no_falla(agente):
    """El hook de cierre se puede llamar siempre, sin sesión abierta."""
    agente.cerrar()  # no debe lanzar
