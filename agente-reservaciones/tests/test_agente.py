"""
Tests del agente (Fase 4, function calling nativo)
==================================================
Prueban la lógica del agente SIN llamar a Gemini ni levantar el servidor
MCP: tanto el cliente de Gemini como el ClienteMCP se reemplazan por dobles
de prueba. Así los tests corren rápido, sin red, sin cuota y sin depender
de que Postgres esté arriba.

Lo que se valida es el bucle de function calling: que el agente ejecute
la tool que Gemini pide (con los argumentos ya parseados por el SDK),
encadene varias si hace falta, conserve los resultados en el historial
(lo que reemplaza al viejo parche del horario_id), y redacte la respuesta
final. La conexión real con Gemini y con las tools está cubierta por los
scripts de scripts/ y por los tests de MCP.
"""

import pytest

from google.genai import types

from app.agente.agent import AgenteReservaciones


# --- Dobles de prueba ---


class _FunctionCallFalso:
    def __init__(self, name, args):
        self.name = name
        self.args = args


class _CandidatoFalso:
    def __init__(self, content):
        self.content = content


class _RespuestaGemini:
    """
    Imita lo que devuelve client.models.generate_content.

    - Un turno que pide tools: function_calls = [..], text = None.
    - Un turno final: function_calls = None, text = "la respuesta".
    """

    def __init__(self, function_calls=None, text=None):
        self.function_calls = function_calls
        self.text = text
        # El agente guarda candidates[0].content en el historial y lo
        # reenvía; el cliente falso ignora los contents, así que alcanza
        # con un objeto centinela.
        self.candidates = [_CandidatoFalso(object())]


class _ClienteGeminiFalso:
    """Devuelve respuestas predefinidas, una por cada generate_content."""

    def __init__(self, respuestas):
        self._respuestas = list(respuestas)
        self.llamadas = []
        self.models = self

    def generate_content(self, **kwargs):
        self.llamadas.append(kwargs)
        return self._respuestas.pop(0)


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


def fc(nombre, **args):
    """Atajo para un function call falso."""
    return _FunctionCallFalso(nombre, args)


@pytest.fixture
def agente(monkeypatch):
    """Agente con el cliente de Gemini y el ClienteMCP reemplazados por dobles."""
    monkeypatch.setenv("GEMINI_API_KEY", "clave-de-prueba")
    monkeypatch.setattr("app.agente.agent.ClienteMCP", _ClienteMCPFalso)
    _ClienteMCPFalso.ejecutadas = []

    a = AgenteReservaciones()

    def usar_respuestas(*respuestas):
        a.client = _ClienteGeminiFalso(respuestas)
        return a

    a.usar_respuestas = usar_respuestas
    return a


# --- Declaración de tools ---


def test_declara_las_cuatro_tools_para_gemini(agente):
    # self._tools es [Tool(function_declarations=[...4...])]
    nombres = {d.name for d in agente._tools[0].function_declarations}
    assert nombres == {
        "buscar_conocimiento",
        "consultar_disponibilidad",
        "crear_reservacion",
        "escalar_caso",
    }


def test_los_parametros_obligatorios_estan_declarados(agente):
    decls = {d.name: d for d in agente._tools[0].function_declarations}
    # El SDK convierte el dict de parámetros en un objeto Schema.
    crear = decls["crear_reservacion"].parameters
    # horario_id y nombre_cliente son obligatorios; telefono/email no.
    assert set(crear.required) == {"horario_id", "nombre_cliente"}


# --- El bucle de function calling ---


@pytest.mark.asyncio
async def test_sin_tool_devuelve_el_texto_directo(agente):
    """Un saludo no dispara tools ni abre MCP."""
    a = agente.usar_respuestas(_RespuestaGemini(text="¡Hola! ¿En qué te ayudo?"))

    respuesta = await a.responder("Hola")

    assert respuesta == "¡Hola! ¿En qué te ayudo?"
    assert _ClienteMCPFalso.ejecutadas == []
    assert len(a.client.llamadas) == 1  # una sola llamada a Gemini


@pytest.mark.asyncio
async def test_ejecuta_la_tool_con_los_argumentos_que_gemini_manda(agente):
    a = agente.usar_respuestas(
        _RespuestaGemini(
            function_calls=[fc("consultar_disponibilidad", fecha="2026-07-25", servicio="corte")]
        ),
        _RespuestaGemini(text="Tenemos las 09:00 y las 10:00 disponibles."),
    )

    respuesta = await a.responder("¿Tenés campo mañana para corte?")

    assert _ClienteMCPFalso.ejecutadas == [
        ("consultar_disponibilidad", {"fecha": "2026-07-25", "servicio": "corte"})
    ]
    assert "09:00" in respuesta
    assert len(a.client.llamadas) == 2  # pedir tool + redactar


@pytest.mark.asyncio
async def test_encadena_consultar_y_reservar_en_un_mismo_turno(agente):
    """Gemini puede pedir una tool, ver el resultado, y pedir la siguiente."""
    a = agente.usar_respuestas(
        _RespuestaGemini(function_calls=[fc("consultar_disponibilidad", fecha="2026-07-25")]),
        _RespuestaGemini(
            function_calls=[fc("crear_reservacion", horario_id=1, nombre_cliente="Ana")]
        ),
        _RespuestaGemini(text="Listo Ana, te agendé a las 09:00."),
    )

    respuesta = await a.responder("Reservame un corte para mañana, soy Ana")

    nombres_ejecutados = [n for n, _ in _ClienteMCPFalso.ejecutadas]
    assert nombres_ejecutados == ["consultar_disponibilidad", "crear_reservacion"]
    assert "agendé" in respuesta


@pytest.mark.asyncio
async def test_el_resultado_de_la_tool_queda_en_el_historial(agente):
    """
    Esto es lo que reemplaza al parche del horario_id: el resultado crudo
    de la tool queda en el historial como function_response, así que en un
    turno futuro el modelo lo tiene disponible.
    """
    a = agente.usar_respuestas(
        _RespuestaGemini(function_calls=[fc("consultar_disponibilidad", fecha="2026-07-25")]),
        _RespuestaGemini(text="Hay dos horarios libres."),
    )

    await a.responder("¿Qué hay mañana?")

    # Busco en el historial una parte con function_response que lleve el resultado.
    respuestas_de_tools = [
        parte.function_response
        for contenido in a.historial
        for parte in getattr(contenido, "parts", [])
        if getattr(parte, "function_response", None) is not None
    ]
    assert len(respuestas_de_tools) == 1
    fr = respuestas_de_tools[0]
    assert fr.name == "consultar_disponibilidad"
    assert fr.response["disponibles"][0]["horario_id"] == 1


@pytest.mark.asyncio
async def test_una_tool_que_falla_no_tumba_el_turno(agente, monkeypatch):
    """Si la tool lanza, el error se le pasa a Gemini como resultado; no explota."""

    async def explota(self, nombre_tool, **kwargs):
        raise RuntimeError("servidor caído")

    monkeypatch.setattr(_ClienteMCPFalso, "ejecutar_tool", explota)

    a = agente.usar_respuestas(
        _RespuestaGemini(function_calls=[fc("consultar_disponibilidad", fecha="2026-07-25")]),
        _RespuestaGemini(text="Disculpá, no pude consultar la disponibilidad."),
    )

    respuesta = await a.responder("¿Hay campo mañana?")

    assert isinstance(respuesta, str)
    assert "disculpá" in respuesta.lower()


@pytest.mark.asyncio
async def test_corta_si_el_modelo_pide_tools_sin_parar(agente):
    """Un modelo confundido que pide tools para siempre no debe colgar el turno."""
    # Más respuestas-con-tool que el tope, para forzar el corte.
    muchas = [
        _RespuestaGemini(function_calls=[fc("consultar_disponibilidad", fecha="2026-07-25")])
        for _ in range(AgenteReservaciones.MAX_ITERACIONES_TOOLS + 2)
    ]
    a = agente.usar_respuestas(*muchas)

    respuesta = await a.responder("dale")

    # Devuelve un mensaje de cortesía y no hace infinitas llamadas.
    assert "no pude completar" in respuesta.lower()
    assert len(a.client.llamadas) <= AgenteReservaciones.MAX_ITERACIONES_TOOLS + 1


@pytest.mark.asyncio
async def test_arma_el_registro_para_el_logging(agente):
    """Cada turno deja en ultimo_registro lo necesario para el logging (Fase 6)."""
    a = agente.usar_respuestas(
        _RespuestaGemini(function_calls=[fc("consultar_disponibilidad", fecha="2026-07-25")]),
        _RespuestaGemini(text="Tenemos las 09:00 y 10:00."),
    )

    await a.responder("¿Tenés campo mañana?")

    reg = a.ultimo_registro
    assert reg["mensaje_usuario"] == "¿Tenés campo mañana?"
    assert reg["respuesta_agente"] == "Tenemos las 09:00 y 10:00."
    assert reg["tools"][0]["nombre"] == "consultar_disponibilidad"
    assert reg["tools"][0]["input"] == {"fecha": "2026-07-25"}
    assert reg["tools"][0]["output"]["total"] == 2
    assert reg["latencia_ms"] >= 0


def test_cerrar_no_falla(agente):
    agente.cerrar()  # no debe lanzar
