"""
Agente de Reservaciones
========================
Usa Gemini para interpretar consultas del usuario y ejecutar las tools
apropiadas vía MCP. Es el "cerebro" que decide qué hacer.

Flujo por turno:
    1. El usuario hace una consulta ("¿Tenés turno mañana para corte?").
    2. Gemini decide, en texto, qué tool usar y con qué argumentos, con el
       formato [TOOL: nombre] (args).
    3. El agente parsea ese texto, ejecuta la tool vía MCP, y le devuelve el
       resultado a Gemini para que redacte una respuesta en lenguaje natural.

Ciclo de vida de MCP:
    La sesión MCP se abre y se cierra DENTRO de cada turno (ver ClienteMCP).
    Antes se intentaba mantenerla viva entre turnos, pero eso choca con que
    cada llamada síncrona abre su propio event loop con asyncio.run(): los
    canales de anyio quedan atados al loop donde nacieron y el segundo turno
    fallaba con ClosedResourceError. Abrir/cerrar por turno lo resuelve.
"""

import asyncio
import json
import os
import re
from datetime import datetime

from google import genai
from google.genai import types

from app.agente.cliente_mcp import ClienteMCP


class AgenteReservaciones:
    """Agente que entiende consultas y ejecuta acciones a través de MCP."""

    def __init__(self):
        """Inicializa el cliente de Gemini. La sesión MCP se abre por turno."""
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

        # Historial de la conversación (texto en lenguaje natural).
        self.historial = []

        # Contexto operativo: guarda el resultado CRUDO de la última vez que
        # se ejecutó cada tool en esta conversación. Existe porque el
        # historial solo guarda el texto ya redactado, y ese texto no
        # contiene datos estructurados como horario_id. Sin esto, el agente
        # "olvida" el horario_id apenas Gemini redacta la respuesta bonita, y
        # re-consulta disponibilidad en loop en vez de avanzar a reservar.
        self.contexto_tools: dict = {}

    # --- API pública ---

    def consultar(self, pregunta_usuario: str) -> str:
        """
        Procesa una pregunta y devuelve la respuesta (interfaz síncrona).

        Internamente corre `responder` en su propio event loop. Usar esta
        variante desde código síncrono (una CLI, un script). Desde código
        async (FastAPI) usar `responder` directamente con await.
        """
        return asyncio.run(self.responder(pregunta_usuario))

    async def responder(self, pregunta_usuario: str) -> str:
        """
        Procesa una pregunta de forma asincrónica y devuelve la respuesta.

        Abre una sesión MCP para este turno, ejecuta las tools que Gemini
        pida, y la cierra al terminar (ver ClienteMCP para el porqué).
        """
        self.historial.append({"role": "user", "content": pregunta_usuario})

        prompt_sistema = self._construir_prompt_sistema()

        respuesta = self.client.models.generate_content(
            model=self.modelo,
            contents=[{"role": "user", "parts": [{"text": prompt_sistema}]}]
            + self._convertir_historial_para_gemini(),
            config=types.GenerateContentConfig(safety_settings=self.safety_settings),
        )
        texto_gemini = respuesta.text

        # Solo se abre el servidor MCP si Gemini realmente pidió una tool. Un
        # saludo o una repregunta ("¿me das tu teléfono?") no necesitan tocar
        # la base, así que no pagamos el arranque del subproceso.
        if "[TOOL:" in texto_gemini:
            async with ClienteMCP() as cli:
                resultado_final = await self._procesar_respuesta_gemini(
                    texto_gemini, cli, pregunta_original=pregunta_usuario
                )
        else:
            resultado_final = texto_gemini

        self.historial.append({"role": "assistant", "content": resultado_final})
        return resultado_final

    def cerrar(self) -> None:
        """
        Hook de fin de conversación.

        Hoy no hace falta cerrar nada: la sesión MCP se abre y se cierra
        dentro de cada turno (ver `responder`), no queda nada vivo entre
        preguntas. Se mantiene el método porque las CLIs lo llaman al salir
        y porque es el lugar natural para cualquier limpieza futura.
        """
        return None

    # --- Construcción del prompt ---

    def _construir_prompt_sistema(self) -> str:
        """Define qué es el agente, sus tools, y cómo pedir una ejecución."""
        hoy = datetime.now().strftime("%Y-%m-%d")

        return f"""Eres un agente de IA para un negocio de reservaciones. Hoy es {hoy}.

Tu trabajo es ayudar a los clientes con preguntas, consultar disponibilidad, crear reservaciones,
y escalar casos a un humano cuando sea necesario.

**Tienes estas tools disponibles:**

1. **buscar_conocimiento** - Busca información en la base de conocimiento del negocio
   (políticas, horarios, métodos de pago, ubicación, etc.)
   Args: consulta (string, requerido, el texto de búsqueda), top_k (entero, opcional, default 3)
   Úsala para preguntas sobre el negocio que no sean sobre disponibilidad o reservaciones.

2. **consultar_disponibilidad** - Consulta horarios libres en una fecha específica
   Args: fecha (YYYY-MM-DD requerida), servicio (opcional, ej. "corte", "manicura")
   Úsala cuando el usuario pregunte si hay espacio, cupo o disponibilidad.

3. **crear_reservacion** - Agenda una cita en un horario disponible
   Args: horario_id (obtenido de consultar_disponibilidad), nombre_cliente, telefono (opt), email (opt)
   IMPORTANTE: antes de crear_reservacion, SIEMPRE llama consultar_disponibilidad para obtener el horario_id.
   Nunca inventes un horario_id.

4. **escalar_caso** - Registra un caso para que lo atienda una persona del negocio
   Args: motivo (descripción del problema), nombre_cliente, telefono (recomendado), email (opt)
   Úsala para reclamos, excepciones a políticas, o cuando el usuario pida hablar con alguien.

**Cómo ejecutar tools:**
Cuando decidas que necesitas ejecutar una tool, escribe el comando en este formato exacto:
[TOOL: nombre_tool] (arg1="valor1", arg2=valor2, ...)

Ejemplo 1:
[TOOL: buscar_conocimiento] (consulta="horario de atención")

Ejemplo 2:
[TOOL: consultar_disponibilidad] (fecha="2026-07-25", servicio="corte")

Ejemplo 3:
[TOOL: crear_reservacion] (horario_id=5, nombre_cliente="Juan Pérez", telefono="555-1234")

**Instrucciones importantes:**
- Siempre responde en español, con tono amable y profesional.
- Si no encuentras la información solicitada después de usar las tools, explícale al usuario
  que no está disponible y ofrece alternativas.
- No hagas suposiciones: si necesitas fechas o datos específicos y el usuario no los dio, pídeselos.
- Cuando presentes resultados de tools, hazlo en un lenguaje natural y claro, no devuelvas JSON.
- Mantén el contexto de la conversación: si el usuario ya dio su nombre, úsalo.

**Hoy es {hoy}. Recuerda esto al interpretar fechas relativas (mañana, pasado mañana, etc.).**
{self._construir_contexto_operativo()}
Ahora, ayuda al usuario con su pregunta."""

    def _construir_contexto_operativo(self) -> str:
        """
        Inserta en el prompt los resultados crudos de las tools ya ejecutadas
        en esta conversación, para que Gemini tenga acceso a datos como
        horario_id que el historial en lenguaje natural no conserva.
        """
        if not self.contexto_tools:
            return ""

        bloque = json.dumps(self.contexto_tools, ensure_ascii=False, indent=2)
        return f"""

**Datos ya consultados en esta conversación (contexto interno, NO se lo muestres
al usuario en crudo):**
{bloque}

Usa estos datos si ya tienen lo que necesitas — por ejemplo, si el usuario ya
eligió un horario que vos ya listaste, el horario_id está en
"consultar_disponibilidad" -> "resultado" -> "disponibles". NO vuelvas a llamar
consultar_disponibilidad solo para "recuperar" un horario_id que ya tenés acá;
usalo directamente en crear_reservacion.
"""

    # --- Ejecución de tools ---

    async def _procesar_respuesta_gemini(
        self, texto_gemini: str, cli: ClienteMCP, pregunta_original: str = ""
    ) -> str:
        """
        Busca patrones [TOOL: ...] en la respuesta de Gemini, ejecuta las
        tools contra `cli`, y reemplaza cada comando por su resultado.

        Args:
            texto_gemini: texto devuelto por Gemini.
            cli: sesión MCP abierta para este turno.
            pregunta_original: la pregunta tal como la escribió el usuario,
                para que la segunda llamada a Gemini (la que redacta) sepa
                qué se preguntó y no muestre de más.
        """
        resultado = texto_gemini
        patron = r"\[TOOL: (\w+)\]\s*\((.*?)\)"
        matches = list(re.finditer(patron, resultado))

        # De atrás para adelante, para no desalinear las posiciones al
        # reemplazar cada comando por un texto de largo distinto.
        for match in reversed(matches):
            nombre_tool = match.group(1)
            args_str = match.group(2)

            try:
                args = self._parsear_argumentos(args_str)
                resultado_tool = await cli.ejecutar_tool(nombre_tool, **args)

                # Guardar para turnos futuros (ver contexto_tools en __init__).
                self.contexto_tools[nombre_tool] = {
                    "args": args,
                    "resultado": resultado_tool,
                }

                resultado_json = json.dumps(resultado_tool, ensure_ascii=False, indent=2)
                reemplazo = (
                    f"[Resultado de {nombre_tool}]:\n{resultado_json}\n[Fin resultado]"
                )
            except Exception as e:
                reemplazo = f"Error al ejecutar {nombre_tool}: {e}"

            resultado = resultado[: match.start()] + reemplazo + resultado[match.end() :]

        # Si se ejecutó alguna tool, una segunda llamada a Gemini redacta la
        # respuesta final a partir de los resultados.
        if "[Resultado de" in resultado:
            resultado = await self._gemini_procesar_resultados(
                resultado, pregunta_original
            )

        return resultado

    def _parsear_argumentos(self, args_str: str) -> dict:
        """
        Parsea argumentos de la forma: arg1="valor", arg2=5, arg3=true

        Soporta strings entre comillas, enteros, floats (incluidos negativos)
        y booleanos. Es deliberadamente conservador: si un valor no encaja en
        esos tipos, no se incluye (mejor omitir que pasar basura a la tool).
        """
        args = {}
        patron = r'(\w+)\s*=\s*("[^"]*"|-?\d+\.\d+|-?\d+|true|false)'

        for match in re.finditer(patron, args_str):
            clave = match.group(1)
            valor = match.group(2)

            if valor.startswith('"'):
                valor = valor.strip('"')
            elif valor == "true":
                valor = True
            elif valor == "false":
                valor = False
            elif "." in valor:
                valor = float(valor)
            else:
                valor = int(valor)

            args[clave] = valor

        return args

    async def _gemini_procesar_resultados(
        self, texto_con_resultados: str, pregunta_original: str = ""
    ) -> str:
        """Segunda llamada a Gemini: redacta la respuesta final para el usuario."""
        prompt = f"""El usuario preguntó exactamente esto:

"{pregunta_original}"

Para responderle, se consultaron una o más fuentes de información (tools). Aquí
está el resultado crudo de esas consultas — puede incluir más información de
la que el usuario pidió, porque el buscador (RAG) devuelve varios fragmentos
relacionados aunque solo uno sea relevante:

{texto_con_resultados}

Instrucciones para tu respuesta:
- Respondé ÚNICAMENTE lo que el usuario preguntó. No agregues información
  adicional de los resultados que no fue solicitada, aunque esté disponible.
- Ejemplo: si preguntó solo por el horario de atención, respondé solo el
  horario. No menciones política de cancelación, métodos de pago, ni
  ubicación a menos que también los haya preguntado.
- Sé breve y directo. Un par de líneas suele ser suficiente, no un listado
  con secciones y encabezados.
- No incluyas JSON ni comandos [TOOL] en tu respuesta.
- Si algún resultado fue un error, comunícalo de forma amable y ofrecé
  alternativas.
- Al final, podés ofrecer ayudar con algo más, pero sin adelantar información
  que no se pidió."""

        respuesta = self.client.models.generate_content(
            model=self.modelo,
            contents=prompt,
        )
        return respuesta.text

    def _convertir_historial_para_gemini(self) -> list:
        """Convierte el historial interno al formato de contenidos de Gemini."""
        mensajes = []
        for msg in self.historial:
            rol = "user" if msg["role"] == "user" else "model"
            mensajes.append({"role": rol, "parts": [{"text": msg["content"]}]})
        return mensajes
