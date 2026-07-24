"""
Agente de Reservaciones
========================
Usa Gemini para interpretar consultas del usuario y ejecutar las tools
apropiadas vía MCP. Es el "cerebro" que decide qué hacer.

Flujo:
    1. Usuario hace una consulta (ej. "¿Tenés turno mañana para corte?")
    2. Agente analiza con Gemini qué tool usar
    3. Ejecuta la tool a través del cliente MCP
    4. Procesa la respuesta y devuelve un texto natural

>>> VERSIÓN CON DEBUG <<<
Se agregaron prints y traceback.print_exc() para ver el error real que
estaba quedando oculto por el except genérico. Una vez que encuentres
y arregles el bug, podés quitar las líneas marcadas con "# DEBUG".
"""

import asyncio
import json
import os
import re
import traceback
from datetime import datetime

from google import genai
from google.genai import types

from app.agente.cliente_mcp import ClienteMCP


class AgenteReservaciones:
    """Agente que entiende consultas y ejecuta actions a través de MCP."""

    def __init__(self):
        """Inicializa Gemini y el cliente MCP."""
        # Obtener la API key del .env
        api_key = os.getenv("GEMINI_API_KEY")
        if not api_key:
            raise ValueError("GEMINI_API_KEY no configurada en .env")

        # En el SDK nuevo (google-genai) no existe genai.configure().
        # Se crea un Client una sola vez y se reutiliza.
        self.client = genai.Client(api_key=api_key)

        # Obtener el modelo de .env (por defecto gemini-3.6-flash)
        self.modelo = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

        # Configuración de seguridad relajada (datos de prueba), reutilizable
        self.safety_settings = [
            types.SafetySetting(
                category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HATE_SPEECH",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_HARASSMENT",
                threshold="BLOCK_NONE",
            ),
            types.SafetySetting(
                category="HARM_CATEGORY_DANGEROUS_CONTENT",
                threshold="BLOCK_NONE",
            ),
        ]

        # Inicializar cliente MCP
        self.cliente_mcp = ClienteMCP()

        # Historial de conversación para mantener contexto
        self.historial = []

        # Contexto operativo: guarda el resultado CRUDO de la última vez que
        # se ejecutó cada tool en esta conversación. Existe porque el
        # historial de mensajes solo guarda texto en lenguaje natural, y ese
        # texto no contiene datos estructurados como horario_id. Sin esto,
        # el agente "olvida" el horario_id apenas Gemini redacta la
        # respuesta bonita, y termina re-consultando disponibilidad en un
        # loop en vez de avanzar a crear_reservacion.
        self.contexto_tools: dict = {}

    def consultar(self, pregunta_usuario: str) -> str:
        """
        Procesa una pregunta del usuario y devuelve una respuesta.

        Esta es una interfaz sincrónica que internamente ejecuta código async.

        Args:
            pregunta_usuario: la pregunta tal como la hizo el usuario

        Returns:
            Una respuesta en lenguaje natural
        """
        return asyncio.run(self._consultar_async(pregunta_usuario))

    def cerrar(self):
        """
        Wrapper síncrono de cerrar_sesion(). Llamar UNA SOLA VEZ al terminar
        toda la conversación (ej. al escribir 'salir' o en un except
        KeyboardInterrupt), nunca después de cada pregunta.
        """
        asyncio.run(self.cerrar_sesion())

    async def _consultar_async(self, pregunta_usuario: str) -> str:
        """
        Procesa una pregunta de forma asincrónica.

        Args:
            pregunta_usuario: la pregunta del usuario

        Returns:
            Respuesta en lenguaje natural
        """
        try:
            # Agregar la pregunta al historial
            self.historial.append({"role": "user", "content": pregunta_usuario})

            # Prompt del sistema que define el comportamiento del agente
            prompt_sistema = self._construir_prompt_sistema()

            # Llamar a Gemini con el historial
            respuesta = self.client.models.generate_content(
                model=self.modelo,
                contents=[
                    {"role": "user", "parts": [{"text": prompt_sistema}]},
                ]
                + self._convertir_historial_para_gemini(),
                config=types.GenerateContentConfig(
                    safety_settings=self.safety_settings,
                ),
            )

            # Procesar la respuesta de Gemini
            texto_gemini = respuesta.text

            # Gemini puede decidir llamar a tools. La comunicación es por patrones
            # embebidos en el texto: [TOOL: crear_reservacion] (args)
            resultado_final = await self._procesar_respuesta_gemini(
                texto_gemini, pregunta_original=pregunta_usuario
            )

            # Agregar la respuesta final al historial
            self.historial.append({"role": "assistant", "content": resultado_final})

            return resultado_final

        except Exception:
            # NOTA: ya no hay un `finally` que cierre el cliente MCP acá.
            # Antes se cerraba (y por lo tanto se relanzaba el subprocess
            # completo del servidor MCP) después de CADA pregunta, lo cual
            # era costoso y causaba fallas intermitentes en la primera
            # consulta de una sesión (el servidor recién levantado necesita
            # cargar el modelo de embeddings de Chroma). Ahora la sesión MCP
            # se mantiene viva durante toda la conversación y se cierra una
            # sola vez, explícitamente, con self.cerrar_sesion().
            raise

    async def cerrar_sesion(self):
        """
        Cierra la sesión MCP y el subprocess del servidor.

        Llamar esto UNA SOLA VEZ, al finalizar toda la conversación
        (ej. cuando el usuario escribe 'salir' o al capturar Ctrl+C),
        no después de cada pregunta individual.
        """
        try:
            await self.cliente_mcp.cerrar()
        except Exception:
            pass

    def _construir_prompt_sistema(self) -> str:
        """
        Construye el prompt del sistema que define el comportamiento del agente.

        Define:
        - Qué es el agente
        - Qué tools tiene disponibles y cuándo usar cada una
        - Cómo comunicar que quiere ejecutar una tool
        """

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
        Construye un bloque de texto con los resultados crudos de las tools
        ya ejecutadas en esta conversación (ver self.contexto_tools).

        Esto le da a Gemini acceso a datos estructurados (como horario_id)
        que de otra forma se perderían, porque el historial de mensajes solo
        contiene el texto en lenguaje natural ya redactado, sin esos datos.

        Returns:
            Un string para insertar en el prompt de sistema, vacío si todavía
            no se ejecutó ninguna tool en esta conversación.
        """
        if not self.contexto_tools:
            return ""

        bloque = json.dumps(self.contexto_tools, ensure_ascii=False, indent=2)
        return f"""

**Datos ya consultados en esta conversación (contexto interno, NO se lo muestres
al usuario en crudo):**
{bloque}

Usa estos datos si ya tienen lo que necesitas — por ejemplo, si el usuario ya
eligió un horario y ya diste ese horario antes, el horario_id correspondiente
está en "consultar_disponibilidad" -> "resultado" -> "disponibles". NO vuelvas
a llamar consultar_disponibilidad solo para "recuperar" un horario_id que ya
tenés acá; usalo directamente en crear_reservacion.
"""

    async def _procesar_respuesta_gemini(
        self, texto_gemini: str, pregunta_original: str = ""
    ) -> str:
        """
        Procesa la respuesta de Gemini y ejecuta tools si es necesario.

        Busca patrones [TOOL: ...] en el texto y los ejecuta.

        Args:
            texto_gemini: texto devuelto por Gemini
            pregunta_original: la pregunta tal como la escribió el usuario,
                necesaria para que la segunda llamada a Gemini (la que redacta
                la respuesta final) sepa qué se preguntó y no muestre de más.

        Returns:
            El texto con los comandos de tool reemplazados por sus resultados
        """
        resultado = texto_gemini
        patron = r"\[TOOL: (\w+)\]\s*\((.*?)\)"
        matches = list(re.finditer(patron, resultado))

        # DEBUG ---------------------------------------------------------
        print("=" * 70)
        print("[DEBUG] TEXTO CRUDO DE GEMINI:")
        print(repr(texto_gemini))
        print(f"[DEBUG] Matches de [TOOL: ...] encontrados: {len(matches)}")
        print("=" * 70)
        # -----------------------------------------------------------------

        # Procesar de atrás para adelante para no desalinear posiciones
        for match in reversed(matches):
            nombre_tool = match.group(1)
            args_str = match.group(2)

            # DEBUG -------------------------------------------------
            print(f"[DEBUG] Tool detectada: {nombre_tool!r}")
            print(f"[DEBUG] Args crudos: {args_str!r}")
            # ---------------------------------------------------------

            try:
                # Parsear los argumentos
                args = self._parsear_argumentos(args_str)
                print(f"[DEBUG] Args parseados: {args}")  # DEBUG

                # Ejecutar la tool de forma asincrónica
                resultado_tool = await self.cliente_mcp.ejecutar_tool(nombre_tool, **args)
                print(f"[DEBUG] Resultado crudo de la tool: {resultado_tool}")  # DEBUG

                # Guardar en el contexto operativo para que esté disponible
                # en turnos futuros (ver comentario en __init__)
                self.contexto_tools[nombre_tool] = {
                    "args": args,
                    "resultado": resultado_tool,
                }

                # Convertir el resultado a JSON
                resultado_json = json.dumps(resultado_tool, ensure_ascii=False, indent=2)

                # Reemplazar el comando con el resultado
                reemplazo = (
                    f"[Resultado de {nombre_tool}]:\n{resultado_json}\n[Fin resultado]"
                )
                resultado = (
                    resultado[: match.start()]
                    + reemplazo
                    + resultado[match.end() :]
                )

            except Exception as e:
                # DEBUG: acá es donde se estaba tragando el error real.
                # Este print + traceback te va a mostrar la excepción completa
                # en la consola, con el archivo y línea exactos donde truena.
                print(f"[DEBUG] EXCEPCIÓN REAL al ejecutar {nombre_tool}:")
                traceback.print_exc()

                # Si la tool falla, reemplazar con un mensaje de error
                error_msg = f"Error al ejecutar {nombre_tool}: {str(e)}"
                resultado = resultado[: match.start()] + error_msg + resultado[match.end() :]

        # Si hay resultados embebidos, hacer otra llamada a Gemini
        if "[Resultado de" in resultado:
            resultado = await self._gemini_procesar_resultados(
                resultado, pregunta_original
            )

        return resultado

    def _parsear_argumentos(self, args_str: str) -> dict:
        """
        Parsea una cadena de argumentos de la forma:
            arg1="valor", arg2=5, telefono="123-456"

        Args:
            args_str: string con los argumentos

        Returns:
            dict con los argumentos parseados
        """
        args = {}
        patron = r'(\w+)=(".*?"|\d+|true|false)'

        for match in re.finditer(patron, args_str):
            clave = match.group(1)
            valor = match.group(2)

            # Procesar el valor
            if valor.startswith('"'):
                valor = valor.strip('"')
            elif valor == "true":
                valor = True
            elif valor == "false":
                valor = False
            else:
                try:
                    valor = int(valor)
                except ValueError:
                    valor = float(valor)

            args[clave] = valor

        return args

    async def _gemini_procesar_resultados(
        self, texto_con_resultados: str, pregunta_original: str = ""
    ) -> str:
        """
        Segunda llamada a Gemini para que procese los resultados de las tools.

        Args:
            texto_con_resultados: texto que contiene [Resultado de ...] embebido
            pregunta_original: la pregunta tal como la escribió el usuario

        Returns:
            Respuesta limpia sin los comandos de tool
        """
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
        """Convierte el historial de conversación al formato de Gemini."""
        mensajes = []
        for msg in self.historial:
            rol = "user" if msg["role"] == "user" else "model"
            mensajes.append({"role": rol, "parts": [{"text": msg["content"]}]})
        return mensajes