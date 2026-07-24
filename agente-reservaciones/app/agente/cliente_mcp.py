"""
Cliente MCP
===========
Conecta con el servidor MCP vía subprocess (stdio) para ejecutar tools.

El servidor corre como un proceso separado, y este cliente se comunica
con él usando mcp.client.stdio + mcp.ClientSession.

Ciclo de vida: se usa como context manager async, ABIERTO Y CERRADO
DENTRO DE UNA MISMA CORRUTINA (una misma tarea de asyncio):

    async with ClienteMCP() as cli:
        resultado = await cli.ejecutar_tool("consultar_disponibilidad", fecha="...")

¿Por qué así y no una sesión persistente entre preguntas?
    La sesión MCP usa anyio por debajo, y anyio ata sus canales a la tarea
    y al event loop donde nacieron. Si se abre en un `asyncio.run()` y se
    intenta reutilizar en otro `asyncio.run()` posterior (un loop distinto),
    revienta con `ClosedResourceError` o "cancel scope in a different task".
    Por eso todo el ciclo —abrir, ejecutar, cerrar— vive dentro de la misma
    corrutina. El costo es relanzar el subproceso del servidor por turno;
    a cambio, es robusto y no arrastra estado entre loops.

    (Una sesión realmente persistente y sin ese costo es posible, pero
    requiere un event loop dedicado en un hilo aparte. Queda como mejora
    futura si el relanzado por turno llegara a molestar.)
"""

import json
import sys
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Asegurar que la raíz del proyecto esté en sys.path para que el servidor
# (lanzado como `python -m app.mcp_server.server`) encuentre el paquete.
_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))


class ClienteMCP:
    """Cliente MCP de vida corta: se abre y se cierra dentro de un mismo turno."""

    def __init__(self):
        self.sesion: Optional[ClientSession] = None
        self._stack: Optional[AsyncExitStack] = None

    async def __aenter__(self) -> "ClienteMCP":
        """Lanza el subproceso del servidor MCP y hace el handshake."""
        self._stack = AsyncExitStack()
        try:
            parametros = StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.mcp_server.server"],
            )
            lectura, escritura = await self._stack.enter_async_context(
                stdio_client(parametros)
            )
            self.sesion = await self._stack.enter_async_context(
                ClientSession(lectura, escritura)
            )
            await self.sesion.initialize()
            return self
        except BaseException:
            # Si algo falla a mitad de la apertura, cerrar lo que se haya
            # abierto antes de propagar el error.
            await self._stack.aclose()
            self._stack = None
            self.sesion = None
            raise

    async def __aexit__(self, *exc) -> None:
        if self._stack is not None:
            await self._stack.aclose()
        self._stack = None
        self.sesion = None

    async def ejecutar_tool(self, nombre_tool: str, **kwargs) -> dict:
        """
        Ejecuta una tool en el servidor MCP y devuelve su resultado como dict.

        Args:
            nombre_tool: nombre de la tool (ej. "crear_reservacion").
            **kwargs: argumentos de la tool.

        Returns:
            El resultado de la tool ya parseado a dict. Las tools de este
            proyecto devuelven JSON, así que casi siempre es el dict directo;
            si por lo que sea no fuera JSON, se envuelve en {"resultado": ...}.
        """
        if self.sesion is None:
            raise RuntimeError(
                "ClienteMCP no está abierto. Usalo con 'async with ClienteMCP() as cli:'."
            )

        resultado = await self.sesion.call_tool(nombre_tool, arguments=kwargs)

        if resultado.content:
            contenido = resultado.content[0]
            texto = getattr(contenido, "text", None)
            if texto is not None:
                try:
                    return json.loads(texto)
                except (json.JSONDecodeError, ValueError):
                    return {"resultado": texto}

        return {"error": "El servidor MCP no devolvió contenido."}
