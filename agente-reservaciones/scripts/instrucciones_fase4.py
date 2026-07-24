"""
INSTRUCCIONES PARA PROBAR FASE 4
==================================

La Fase 4 conecta Gemini al servidor MCP. El agente ahora puede:
- Recibir una pregunta del usuario
- Decidir qué tool ejecutar
- Ejecutarla a través del MCP
- Devolver una respuesta natural

ANTES DE EMPEZAR:
=================
1. Asegúrate de tener PostgreSQL corriendo:
   docker compose up -d postgres

2. Verifica que la BD está poblada:
   python -m app.db.seed

3. Verifica que el vector store está listo:
   python -m app.rag.ingest

4. Verifica que GEMINI_API_KEY está en .env:
   GEMINI_API_KEY=tu_clave_aqui
   GEMINI_MODEL=gemini-3.6-flash

OPCIÓN 1: Test manual interactivo
==================================
Ejecuta este script para tener un chat interactivo con el agente:

    python tests/test_agente.py

Ejemplo de preguntas que puedes hacer:
    "¿Qué servicios ofrecen?"
    "¿Tengo disponibilidad para corte mañana?"
    "Quiero reservar un turno"
    "¿Cuál es el horario de atención?"
    "Necesito cancelar mi cita"

OPCIÓN 2: API HTTP
===================
Levanta el servidor FastAPI:

    python -m uvicorn app.main:app --reload --port 8000

Luego prueba con curl o Postman:

    # Health check
    curl http://localhost:8000/estado

    # Procesar una consulta
    curl -X POST http://localhost:8000/consulta \
      -H "Content-Type: application/json" \
      -d '{"pregunta": "¿Hay disponibilidad mañana para corte?"}'

    # Documentación interactiva
    http://localhost:8000/docs

OPCIÓN 3: Programáticamente
=============================
Desde Python:

    from app.agente.agent import AgenteReservaciones

    agente = AgenteReservaciones()
    respuesta = agente.consultar("¿Tenés turno mañana?")
    print(respuesta)

CÓMO FUNCIONA
==============
1. El agente recibe una pregunta
2. La envía a Gemini con un prompt que define las tools disponibles
3. Gemini decide si necesita ejecutar alguna tool
4. Si sí, devuelve un comando como: [TOOL: nombre] (arg1="valor", arg2=valor)
5. El agente ejecuta la tool a través del ClienteMCP (que se conecta al servidor MCP)
6. El resultado se envía nuevamente a Gemini
7. Gemini genera una respuesta natural en español
8. El agente devuelve esa respuesta al usuario

TROUBLESHOOTING
================

Error: "GEMINI_API_KEY no configurada en .env"
→ Asegúrate de agregar GEMINI_API_KEY a .env

Error: "La base de conocimiento está vacía"
→ Ejecuta: python -m app.rag.ingest

Error: "PostgreSQL not available"
→ Ejecuta: docker compose up -d postgres

Error: "El servidor MCP se ha detenido"
→ Esto es normal si el servidor falla. El ClienteMCP lo reinicia automáticamente.
  Si persiste, revisa que el servidor MCP funciona:
    python app/mcp_server/server.py

LOGS Y DEBUGGING
=================
El agente imprime:
- El prompt que envía a Gemini
- Los comandos de tool que detecta
- Los resultados de las tools
- Cualquier error que ocurra

Para ver más detalles, puedes:
1. Agregar print() en app/agente/agent.py
2. Ver los logs de FastAPI si usas la opción HTTP
3. Ejecutar con LOG_LEVEL=DEBUG si lo necesitas

NOTAS
======
- El agente mantiene el historial de conversación
- Cada llamada a Gemini cuesta dinero (aunque sea poco en la capa gratuita)
- El servidor MCP se lanza automáticamente desde el ClienteMCP
- No es necesario hacer nada especial: el agente maneja todo

¡Listo! Ahora puedes probar la Fase 4. 🚀
"""

# Este archivo es solo documentación, se ejecuta así:
# python tests/instrucciones_fase4.py
# O simplemente léelo para saber cómo probar la Fase 4

if __name__ == "__main__":
    print(__doc__)
