"""
Agente de Reservaciones - Core MCP
====================================
Punto de entrada del paquete principal. La app está separada en módulos
independientes para que el "corazón" (agente + MCP + RAG + eval) se pueda
usar desde cualquier canal (web, WhatsApp, etc.) sin reescribir lógica.

Acá se carga el archivo .env, antes que cualquier otro módulo del
paquete, para que `os.environ` ya tenga los valores cuando se importe
app.db.session (que lee DATABASE_URL al importarse).
"""

from dotenv import load_dotenv

from .rutas import RAIZ_PROYECTO

# Ruta absoluta a propósito: al servidor MCP lo lanza un cliente externo
# desde cualquier directorio, y con una ruta relativa no encontraría el
# archivo (ver app/rutas.py).
#
# `override=False` (el valor por defecto) hace que las variables ya
# definidas en el entorno real ganen sobre las del archivo. Es lo que
# permite que dentro de Docker mande el `environment:` del compose y no
# este .env, que apunta a localhost.
load_dotenv(RAIZ_PROYECTO / ".env", override=False)
