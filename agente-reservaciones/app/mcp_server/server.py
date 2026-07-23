"""
Servidor MCP
============
Expone las tools del negocio vía Model Context Protocol, para que
cualquier cliente compatible (Claude Desktop, Claude Code, un cliente
propio con el SDK) las pueda descubrir y ejecutar.

Se usa FastMCP: el decorador `@mcp.tool()` genera el JSON Schema de cada
tool leyendo los type hints y el docstring de la función. Por eso los
docstrings de este archivo no son documentación interna -- son
literalmente el texto que el modelo lee para decidir si una tool le sirve
y con qué argumentos llamarla.

Las funciones de acá son envoltorios delgados sobre `app/tools/`: la
lógica de negocio vive allá y se prueba sin MCP de por medio. Este
archivo solo se encarga del protocolo.

Uso:
    python -m app.mcp_server.server        (parado en la raíz del proyecto)
    python app/mcp_server/server.py        (desde cualquier directorio)
"""

import sys
from pathlib import Path

# El cliente MCP (Claude Desktop, Claude Code, ...) lanza este archivo
# desde el directorio que se le antoje, y ahí `import app.*` falla porque
# la raíz del proyecto no está en sys.path. Se agrega antes de importar
# nada del proyecto -- por eso este bloque va arriba de los imports.
_RAIZ = Path(__file__).resolve().parents[2]
if str(_RAIZ) not in sys.path:
    sys.path.insert(0, str(_RAIZ))

from app.tools.buscar_conocimiento import buscar_conocimiento as _buscar_conocimiento
from app.tools.consultar_disponibilidad import (
    consultar_disponibilidad as _consultar_disponibilidad,
)

from mcp.server.fastmcp import FastMCP

mcp = FastMCP("agente-reservaciones")


@mcp.tool()
def buscar_conocimiento(consulta: str, top_k: int = 3) -> dict:
    """
    Busca información en la base de conocimiento del negocio.

    Úsala para responder preguntas sobre políticas, horarios de atención,
    métodos de pago, ubicación y cualquier otra información general que
    esté documentada. NO sirve para consultar disponibilidad de citas ni
    para reservar: eso son otras tools.

    Args:
        consulta: la pregunta del usuario, en lenguaje natural.
        top_k: cuántos fragmentos relevantes devolver (por defecto 3).

    Returns:
        Los fragmentos más relevantes encontrados, cada uno con su texto y
        el documento del que salió.
    """
    return _buscar_conocimiento(consulta=consulta, top_k=top_k)


@mcp.tool()
def consultar_disponibilidad(fecha: str, servicio: str | None = None) -> dict:
    """
    Consulta qué horarios están libres para reservar en una fecha.

    Úsala cuando el usuario pregunte si hay campo, cupo o espacio libre, o
    cuando quiera agendar algo y haya que confirmar la disponibilidad
    antes de crear la reservación.

    Args:
        fecha: la fecha a consultar en formato YYYY-MM-DD (ej. "2026-08-01").
        servicio: nombre del servicio a filtrar (ej. "corte"). Si se omite,
            devuelve los horarios libres de todos los servicios. No hace
            falta el nombre exacto: busca por coincidencia parcial.

    Returns:
        La lista de horarios disponibles. Cada uno incluye su `horario_id`,
        que es el dato necesario para crear después la reservación.
    """
    return _consultar_disponibilidad(fecha=fecha, servicio=servicio)


if __name__ == "__main__":
    # stdio es el transporte estándar para servidores MCP locales: el
    # cliente lanza este proceso y se comunica por stdin/stdout. Por eso
    # este archivo NUNCA debe imprimir nada a stdout por su cuenta -- eso
    # corrompería el canal del protocolo.
    mcp.run(transport="stdio")
