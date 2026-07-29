"""
Agente de Reservaciones
========================
Usa Gemini (con function calling nativo) para interpretar consultas del
usuario y ejecutar las tools apropiadas vía MCP. Es el "cerebro" que
decide qué hacer.

Flujo de un turno:
    1. El usuario hace una consulta ("¿Tenés turno mañana para corte?").
    2. Se le manda a Gemini junto con las DECLARACIONES de las 4 tools.
    3. Si Gemini decide usar una tool, devuelve una llamada estructurada
       (nombre + argumentos ya parseados por el SDK, sin regex).
    4. El agente ejecuta esa tool vía MCP, le devuelve el resultado a
       Gemini, y este redacta la respuesta final en lenguaje natural. Si
       hace falta encadenar tools (consultar y después reservar), el ciclo
       se repite.

Por qué function calling nativo y no un patrón de texto:
    Antes el agente le pedía a Gemini que escribiera "[TOOL: nombre](args)"
    y parseaba ese texto con una expresión regular. Eso es frágil (el
    modelo tiene que formatear exacto, el parser no cubre todos los casos)
    y encima perdía datos entre turnos: el historial solo guardaba el
    texto redactado, así que el horario_id se "olvidaba" y hacía falta un
    parche. Con function calling nativo el SDK entrega los argumentos ya
    parseados, y el historial conserva las llamadas y respuestas de tools,
    así que el modelo recuerda el horario_id solo.

Ciclo de vida de MCP:
    La sesión MCP se abre y se cierra DENTRO de cada turno (ver ClienteMCP),
    y solo si Gemini realmente pide una tool. Un saludo no toca la base.
"""

import asyncio
import os
import time
from datetime import datetime

from google import genai
from google.genai import types

from app.agente.cliente_mcp import ClienteMCP


class AgenteReservaciones:
    """Agente que entiende consultas y ejecuta acciones a través de MCP."""

    # Tope de vueltas del ciclo de tools en un mismo turno. Evita que un
    # modelo confundido quede pidiendo tools para siempre (y gastando cuota).
    MAX_ITERACIONES_TOOLS = 6

    def __init__(self):
        """Inicializa el cliente de Gemini y las declaraciones de tools."""
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY no configurada en .env")

        # En el SDK google-genai no existe genai.configure(): se crea un
        # Client una vez y se reutiliza.
        self.client = genai.Client(api_key=api_key)
        self.modelo = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

        # Seguridad relajada: son datos de prueba, no queremos que un falso
        # positivo del filtro corte una respuesta legítima.
        self.safety_settings = [
            types.SafetySetting(category=c, threshold="BLOCK_NONE")
            for c in (
                "HARM_CATEGORY_SEXUALLY_EXPLICIT",
                "HARM_CATEGORY_HATE_SPEECH",
                "HARM_CATEGORY_HARASSMENT",
                "HARM_CATEGORY_DANGEROUS_CONTENT",
            )
        ]

        # Declaraciones de las tools en formato Gemini. Se arman una vez.
        self._tools = self._declarar_tools()

        # Historial de la conversación como objetos Content de Gemini. A
        # diferencia del enfoque anterior, incluye los turnos de function
        # call y function response, así que el modelo conserva datos
        # estructurados (como horario_id) entre un turno y el siguiente.
        self.historial: list[types.Content] = []

        # Tokens que consumió el ÚLTIMO turno (sumando todas las llamadas a
        # Gemini de ese turno). Lo usa la evaluación para medir costo y sirve
        # de base para el logging. Se reinicia en cada `responder`.
        self.ultimo_uso = {"tokens_entrada": 0, "tokens_salida": 0, "tokens_total": 0}

        # Registro completo del ÚLTIMO turno, para el logging (Fase 6): la
        # pregunta, las tools ejecutadas (con su input y output), la respuesta,
        # los tokens y la latencia. El agente NO lo persiste solo — lo expone
        # para que el llamador (la API) lo registre; así los tests y la
        # evaluación pueden usar el agente sin escribir en la base.
        self.ultimo_registro: dict = {}

    # --- API pública ---

    def consultar(self, pregunta_usuario: str) -> str:
        """
        Procesa una pregunta y devuelve la respuesta (interfaz síncrona).

        Corre `responder` en su propio event loop. Usar esta variante desde
        código síncrono (una CLI, un script). Desde código async (FastAPI)
        usar `responder` directamente con await.
        """
        return asyncio.run(self.responder(pregunta_usuario))

    async def responder(self, pregunta_usuario: str) -> str:
        """
        Procesa una pregunta de forma asincrónica y devuelve la respuesta.

        Le pasa a Gemini el historial + las tools. Si Gemini pide tools,
        abre una sesión MCP para este turno, las ejecuta (encadenando si
        hace falta), y devuelve la redacción final. La sesión MCP se cierra
        al terminar (ver ClienteMCP para el porqué).
        """
        inicio = time.monotonic()
        self.ultimo_uso = {"tokens_entrada": 0, "tokens_salida": 0, "tokens_total": 0}
        tools_llamadas: list[dict] = []

        self.historial.append(
            types.Content(role="user", parts=[types.Part(text=pregunta_usuario)])
        )

        config = types.GenerateContentConfig(
            tools=self._tools,
            system_instruction=self._prompt_sistema(),
            safety_settings=self.safety_settings,
        )

        respuesta = self.client.models.generate_content(
            model=self.modelo, contents=self.historial, config=config
        )
        self._acumular_uso(respuesta)

        # Sin tools: el modelo respondió directo (saludo, repregunta, etc.).
        # No se abre MCP.
        if not respuesta.function_calls:
            texto = self._cerrar_turno(respuesta)
        else:
            # Con tools: se abre MCP y se corre el ciclo llamar → ejecutar →
            # devolver resultado → repetir, hasta que el modelo redacte sin
            # pedir más tools (o hasta el tope de iteraciones).
            async with ClienteMCP() as cli:
                iteraciones = 0
                while respuesta.function_calls and iteraciones < self.MAX_ITERACIONES_TOOLS:
                    iteraciones += 1

                    # Guardar el turno del modelo (los function_call) en el historial.
                    contenido_modelo = self._contenido(respuesta)
                    if contenido_modelo is not None:
                        self.historial.append(contenido_modelo)

                    # Ejecutar cada tool pedida y juntar sus resultados. Gemini
                    # puede pedir varias tools de una; se responden todas juntas.
                    partes_resultado = []
                    for fc in respuesta.function_calls:
                        entrada = dict(fc.args) if fc.args else {}
                        salida = await self._ejecutar_tool(cli, fc)
                        tools_llamadas.append(
                            {"nombre": fc.name, "input": entrada, "output": salida}
                        )
                        partes_resultado.append(
                            types.Part.from_function_response(
                                name=fc.name, response=salida
                            )
                        )
                    self.historial.append(
                        types.Content(role="user", parts=partes_resultado)
                    )

                    respuesta = self.client.models.generate_content(
                        model=self.modelo, contents=self.historial, config=config
                    )
                    self._acumular_uso(respuesta)

            texto = self._cerrar_turno(respuesta)

        self.ultimo_registro = {
            "mensaje_usuario": pregunta_usuario,
            "tools": tools_llamadas,
            "respuesta_agente": texto,
            "tokens_entrada": self.ultimo_uso["tokens_entrada"],
            "tokens_salida": self.ultimo_uso["tokens_salida"],
            "tokens_total": self.ultimo_uso["tokens_total"],
            "latencia_ms": int((time.monotonic() - inicio) * 1000),
        }
        return texto

    def cerrar(self) -> None:
        """
        Hook de fin de conversación.

        Hoy no hace falta cerrar nada: la sesión MCP se abre y se cierra
        dentro de cada turno (ver `responder`). Se mantiene el método porque
        las CLIs lo llaman al salir y es el lugar natural para limpieza futura.
        """
        return None

    # --- Internos ---

    def _cerrar_turno(self, respuesta) -> str:
        """
        Cierra un turno: guarda el turno final del modelo en el historial y
        devuelve el texto para el usuario.

        Si el modelo se quedó pidiendo tools tras el tope de iteraciones, o
        la respuesta no trae texto, devuelve un mensaje de cortesía en vez
        de un texto vacío.
        """
        if respuesta.function_calls:
            # Llegó al tope todavía pidiendo tools: no hay una respuesta
            # redactada que darle al usuario.
            return (
                "Disculpá, no pude completar la operación en este momento. "
                "¿Podés intentarlo de nuevo?"
            )

        contenido = self._contenido(respuesta)
        if contenido is not None:
            self.historial.append(contenido)

        texto = getattr(respuesta, "text", None)
        return texto or "Disculpá, no tengo una respuesta para eso ahora mismo."

    async def _ejecutar_tool(self, cli: ClienteMCP, function_call) -> dict:
        """
        Ejecuta una tool pedida por Gemini y devuelve su resultado como dict.

        Si la ejecución falla (por ejemplo, el servidor MCP no responde), se
        devuelve el error como dato — así el modelo lo recibe como resultado
        de la tool y puede recuperarse (ofrecer otra cosa, disculparse), en
        vez de que el turno explote.
        """
        try:
            argumentos = dict(function_call.args) if function_call.args else {}
            return await cli.ejecutar_tool(function_call.name, **argumentos)
        except Exception as e:
            return {"error": f"No se pudo ejecutar {function_call.name}: {e}"}

    def _acumular_uso(self, respuesta) -> None:
        """Suma los tokens de una respuesta de Gemini al contador del turno."""
        uso = getattr(respuesta, "usage_metadata", None)
        if uso is None:
            return
        self.ultimo_uso["tokens_entrada"] += uso.prompt_token_count or 0
        self.ultimo_uso["tokens_salida"] += uso.candidates_token_count or 0
        self.ultimo_uso["tokens_total"] += uso.total_token_count or 0

    @staticmethod
    def _contenido(respuesta):
        """Devuelve candidates[0].content de forma segura, o None si no hay."""
        candidatos = getattr(respuesta, "candidates", None)
        if candidatos:
            return candidatos[0].content
        return None

    def _declarar_tools(self) -> list[types.Tool]:
        """
        Declara las 4 tools del negocio en formato Gemini.

        Los esquemas son deliberadamente simples (solo string/integer, y los
        opcionales se marcan omitiéndolos de `required`): el function calling
        de Gemini es más estricto que JSON Schema y rechaza construcciones
        como `anyOf` o `null`. Las descripciones son lo que Gemini lee para
        decidir qué tool usar, así que están escritas para el modelo.
        """
        declaraciones = [
            types.FunctionDeclaration(
                name="buscar_conocimiento",
                description=(
                    "Busca información en la base de conocimiento del negocio: "
                    "políticas, horarios de atención, métodos de pago, ubicación "
                    "y demás información general documentada. Úsala para preguntas "
                    "sobre el negocio que NO sean de disponibilidad ni de reservar."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "consulta": {
                            "type": "string",
                            "description": "La pregunta del usuario, en lenguaje natural.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Cuántos fragmentos relevantes traer (por defecto 3).",
                        },
                    },
                    "required": ["consulta"],
                },
            ),
            types.FunctionDeclaration(
                name="consultar_disponibilidad",
                description=(
                    "Consulta qué horarios están libres para reservar en una fecha. "
                    "Úsala cuando el usuario pregunte si hay campo, cupo o espacio, o "
                    "antes de reservar para confirmar la disponibilidad. Devuelve el "
                    "horario_id de cada espacio libre, necesario para crear la reserva."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "fecha": {
                            "type": "string",
                            "description": "Fecha a consultar en formato YYYY-MM-DD (ej. 2026-08-01).",
                        },
                        "servicio": {
                            "type": "string",
                            "description": "Nombre del servicio a filtrar (ej. 'corte'). Opcional; "
                            "acepta coincidencia parcial.",
                        },
                    },
                    "required": ["fecha"],
                },
            ),
            types.FunctionDeclaration(
                name="crear_reservacion",
                description=(
                    "Agenda una reservación en un horario disponible. Úsala cuando el "
                    "usuario confirme que quiere reservar. Necesitás el horario_id, que "
                    "da consultar_disponibilidad: nunca lo inventes ni asumas que un "
                    "horario sigue libre, esta tool lo verifica y avisa si ya se ocupó."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "horario_id": {
                            "type": "integer",
                            "description": "Id del horario a reservar, tal como lo devolvió "
                            "consultar_disponibilidad.",
                        },
                        "nombre_cliente": {
                            "type": "string",
                            "description": "Nombre de la persona que reserva.",
                        },
                        "telefono": {
                            "type": "string",
                            "description": "Teléfono del cliente (opcional pero recomendado).",
                        },
                        "email": {
                            "type": "string",
                            "description": "Correo del cliente (opcional).",
                        },
                    },
                    "required": ["horario_id", "nombre_cliente"],
                },
            ),
            types.FunctionDeclaration(
                name="escalar_caso",
                description=(
                    "Registra un caso para que una persona del negocio lo atienda. LLAMÁ "
                    "esta tool apenas el usuario exprese un reclamo o una queja, reporte un "
                    "cobro incorrecto o pida un reintegro, se muestre insatisfecho con el "
                    "servicio, o pida hablar con una persona, humano o encargado. Es la vía "
                    "para todo lo que no resuelven las otras tools: NO trates un reclamo "
                    "como una consulta de información ni intentes resolverlo vos. Para "
                    "registrar el caso necesitás el nombre real del cliente: si todavía no "
                    "te lo dio, pedíselo PRIMERO (no inventes un nombre) y llamá esta tool "
                    "UNA sola vez, cuando ya lo tengas. No la uses para preguntas del "
                    "negocio (esas van a buscar_conocimiento) ni para reservar."
                ),
                parameters={
                    "type": "object",
                    "properties": {
                        "motivo": {
                            "type": "string",
                            "description": "Qué necesita el usuario y por qué no se pudo "
                            "resolver, con detalle suficiente para quien lo atienda después.",
                        },
                        "nombre_cliente": {
                            "type": "string",
                            "description": "Nombre de la persona.",
                        },
                        "telefono": {
                            "type": "string",
                            "description": "Teléfono de contacto (pedilo si no lo tenés).",
                        },
                        "email": {
                            "type": "string",
                            "description": "Correo de contacto (opcional).",
                        },
                    },
                    "required": ["motivo", "nombre_cliente"],
                },
            ),
        ]
        return [types.Tool(function_declarations=declaraciones)]

    def _prompt_sistema(self) -> str:
        """
        Instrucción de sistema: define el rol, las reglas de negocio y el
        estilo de respuesta. Ya NO le dice a Gemini cómo formatear las
        llamadas a tools — de eso se encarga el function calling nativo.
        """
        hoy = datetime.now().strftime("%Y-%m-%d")
        return f"""Sos un asistente de un negocio de reservaciones (un salón). Hoy es {hoy}.

Ayudás a los clientes a resolver dudas del negocio, consultar disponibilidad, agendar
citas y escalar casos a una persona cuando hace falta. Tenés tools para eso; usalas
cuando corresponda en vez de inventar información.

Reglas de negocio:
- Antes de crear una reservación SIEMPRE tenés que tener un horario_id real que haya
  devuelto consultar_disponibilidad. Nunca lo inventes.
- Si el usuario expresa un reclamo, una queja, un problema con un cobro, insatisfacción,
  o pide hablar con una persona, tu objetivo es registrar el caso con escalar_caso —
  no lo trates como una consulta ni intentes resolverlo vos. Pero registralo UNA SOLA
  VEZ, y solo cuando YA TENGAS el nombre del cliente. Si todavía no te lo dio, pedíselo
  PRIMERO y NO llames a escalar_caso hasta tenerlo. Nunca inventes un nombre, y nunca
  registres el mismo caso dos veces.
- Si te falta un dato para hacer algo (una fecha, el nombre, el teléfono), pedíselo al
  usuario en vez de suponerlo.
- Interpretá las fechas relativas ("mañana", "el jueves") tomando como referencia que
  hoy es {hoy}.

Estilo:
- Respondé siempre en español, con tono amable y profesional, y de forma breve.
- Respondé solo lo que el usuario preguntó. Si una tool te devuelve más información de
  la que se pidió (por ejemplo, el buscador trae varios fragmentos), usá solo lo
  relevante; no vuelques todo.
- No muestres JSON ni detalles internos: redactá en lenguaje natural.
- Cuando escales un caso o crees una reserva, confirmáselo al usuario con los datos
  relevantes (número de reserva o de ticket)."""
