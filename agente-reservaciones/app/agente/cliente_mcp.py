"""
Cliente MCP
===========
Conecta con el servidor MCP vía subprocess (stdio) para ejecutar tools.

El servidor corre como un proceso separado, y este cliente se comunica
con él usando la biblioteca mcp.client.stdio + mcp.ClientSession.

Diseño: El cliente usa una AsyncExitStack para manejar el contexto completo
(subproceso + canales + sesión). La inicialización es lazy - el subproceso
se lanza la primera vez que se ejecuta una tool. La sesión permanece abierta
durante toda la vida del cliente y se cierra explícitamente con cerrar().

Importante: Uso en contextos síncronos (asyncio.run):
    cliente = ClienteMCP()
    resultado = asyncio.run(cliente.ejecutar_tool(...))
    asyncio.run(cliente.cerrar())
"""

import json
import sys
import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
from typing import Optional

from mcp import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client

# Asegurar que la raíz del proyecto esté en sys.path
_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))


class ClienteMCP:
    """Cliente MCP que ejecuta tools en el servidor MCP."""

    def __init__(self):
        """
        Inicializa el cliente. El subproceso se lanza lazy en _inicializar().
        
        El cliente mantiene una AsyncExitStack que permanece abierta durante
        toda la vida útil del cliente, lo que permite manejar contextos
        complejos correctamente incluso cuando se usa con asyncio.run().
        """
        self.cliente: Optional[ClientSession] = None
        self._inicializado = False
        self._stack: AsyncExitStack = AsyncExitStack()
        self._stdio_context = None

    async def _inicializar(self):
        """Lanza el subproceso del servidor MCP y establece la sesión."""
        if self._inicializado:
            return

        try:
            parametros = StdioServerParameters(
                command=sys.executable,
                args=["-m", "app.mcp_server.server"],
            )

            # Usar stdio_client como context manager
            # mcp==1.28.1: stdio_client() retorna un contexto que proporciona (read, write)
            self._stdio_context = await self._stack.enter_async_context(
                stdio_client(parametros)
            )

            # Crear la sesión MCP con los streams
            self.cliente = await self._stack.enter_async_context(
                ClientSession(self._stdio_context[0], self._stdio_context[1])
            )

            # Inicializar la sesión (handshake MCP)
            await self.cliente.initialize()

            self._inicializado = True

        except Exception as e:
            await self._stack.aclose()
            raise RuntimeError(f"Error inicializando cliente MCP: {str(e)}") from e

    async def ejecutar_tool(self, nombre_tool: str, **kwargs) -> dict:
        """
        Ejecuta una tool en el servidor MCP.

        Args:
            nombre_tool: nombre de la tool (ej. "crear_reservacion")
            **kwargs: argumentos para la tool

        Returns:
            dict con el resultado

        Raises:
            RuntimeError si hay error ejecutando
        """
        if not self._inicializado:
            await self._inicializar()

        if not self.cliente:
            raise RuntimeError("Cliente MCP no inicializado")

        try:
            resultado = await self.cliente.call_tool(nombre_tool, arguments=kwargs)

            # Extraer el contenido de la respuesta
            if resultado.content:
                contenido = resultado.content[0]
                if hasattr(contenido, "text"):
                    try:
                        # Intentar parsear como JSON
                        return json.loads(contenido.text)
                    except (json.JSONDecodeError, ValueError):
                        # Si no es JSON, devolver como string
                        return {"resultado": contenido.text}

            return {"error": "Sin contenido en respuesta"}

        except Exception as e:
            raise RuntimeError(f"Error ejecutando tool {nombre_tool}: {str(e)}") from e

    async def cerrar(self):
        """Cierra la sesión y el subproceso del servidor MCP."""
        try:
            if self._stack:
                await self._stack.aclose()
        except Exception:
            # Ignorar errores al cerrar (ej. GeneratorExit de anyio)
            pass
        finally:
            self.cliente = None
            self._stdio_context = None
            self._inicializado = False