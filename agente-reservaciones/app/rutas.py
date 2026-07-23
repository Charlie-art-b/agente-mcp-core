"""
Rutas del proyecto
==================
Resuelve las rutas a partir de la ubicación de este archivo y no del
directorio de trabajo actual.

Hace falta porque el servidor MCP lo lanza un cliente externo (Claude
Desktop, Claude Code, etc.) desde el directorio que a ese cliente se le
ocurra. Si las rutas fueran relativas al cwd, el servidor buscaría el
vector store en el lugar equivocado y respondería que la base de
conocimiento está vacía, sin ningún error visible.
"""

from pathlib import Path

# app/rutas.py -> app/ -> raíz del proyecto (agente-reservaciones/)
RAIZ_PROYECTO = Path(__file__).resolve().parents[1]

CARPETA_DATOS = RAIZ_PROYECTO / "data"
CARPETA_DOCUMENTOS = CARPETA_DATOS / "documents"
RUTA_CHROMA = CARPETA_DATOS / "chroma_local"
