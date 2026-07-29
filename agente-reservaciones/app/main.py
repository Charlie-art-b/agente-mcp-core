"""
Servidor FastAPI
=================
Expone el agente de IA a través de una API HTTP.

Endpoints:
- POST /consulta - Procesa una consulta del usuario
- GET /estado - Health check del servidor
- POST /chat - Endpoint de chat para conversación continua
- POST /reiniciar - Descarta la conversación actual y arranca una nueva

Para correr:
    python -m uvicorn app.main:app --reload --port 8000
    (asegúrate de estar en la raíz del proyecto)
"""

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from app.agente.agent import AgenteReservaciones
from app.db.session import obtener_sesion
from app.logging.metricas import calcular_metricas
from app.logging.registro import registrar_interaccion

# Crear la app FastAPI
app = FastAPI(
    title="Agente de Reservaciones",
    description="IA que consulta disponibilidad y crea reservaciones",
    version="0.1.0",
)

# Inicializar el agente (una sola instancia para mantener historial)
_agente: Optional[AgenteReservaciones] = None


def obtener_agente() -> AgenteReservaciones:
    """Obtiene o crea la instancia del agente (lazy loading)."""
    global _agente
    if _agente is None:
        _agente = AgenteReservaciones()
    return _agente


# Modelos Pydantic para request/response
class ConsultaRequest(BaseModel):
    """Modelo para una consulta del usuario."""

    pregunta: str

    class Config:
        json_schema_extra = {
            "example": {
                "pregunta": "¿Tenés disponibilidad para un corte mañana a la tarde?"
            }
        }


class ConsultaResponse(BaseModel):
    """Modelo para la respuesta del agente."""

    respuesta: str
    exitoso: bool = True

    class Config:
        json_schema_extra = {
            "example": {
                "respuesta": "Sí, tenemos un corte disponible mañana a las 14:00...",
                "exitoso": True,
            }
        }


class EstadoResponse(BaseModel):
    """Modelo para el estado del servidor."""

    estado: str
    agente_listo: bool


# Rutas
@app.get("/", tags=["Info"])
async def raiz():
    """Endpoint raíz con información del servidor."""
    return {
        "nombre": "Agente de Reservaciones",
        "version": "0.1.0",
        "estado": "funcionando",
        "endpoints": {
            "consulta": "POST /consulta - Procesar una consulta del usuario",
            "estado": "GET /estado - Estado del servidor",
            "chat": "POST /chat - Continuar una conversación",
            "reiniciar": "POST /reiniciar - Arrancar una conversación nueva",
            "docs": "GET /docs - Documentación interactiva",
        },
    }


@app.get("/estado", response_model=EstadoResponse, tags=["Info"])
async def obtener_estado():
    """
    Health check del servidor.

    Verifica que el agente está listo para procesar consultas.
    """
    try:
        agente = obtener_agente()
        return EstadoResponse(estado="ok", agente_listo=True)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al inicializar agente: {e}")


@app.post("/consulta", response_model=ConsultaResponse, tags=["Agente"])
async def consulta(request: ConsultaRequest):
    """
    Procesa una consulta del usuario.

    El agente analiza la pregunta, decide qué tools ejecutar (si es necesario),
    las ejecuta, y devuelve una respuesta en lenguaje natural.

    Args:
        request: objeto con el campo 'pregunta'

    Returns:
        ConsultaResponse con la respuesta del agente

    Raises:
        HTTPException: si hay error al procesar la consulta
    """
    if not request.pregunta or not request.pregunta.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía")

    try:
        agente = obtener_agente()
        # `responder` es la variante async: se hace await directamente porque
        # ya estamos dentro del event loop de uvicorn. Llamar el `consultar`
        # síncrono acá reventaría ("asyncio.run() cannot be called from a
        # running event loop").
        respuesta = await agente.responder(request.pregunta)

        # Registrar la interacción (Fase 6). Best-effort: si el logging falla
        # —por ejemplo, la base no está disponible— no debe tumbar la
        # respuesta que ya tenemos para el usuario.
        try:
            registrar_interaccion(agente.ultimo_registro)
        except Exception as e:
            print(f"[logging] no se pudo registrar la interacción: {e}")

        return ConsultaResponse(respuesta=respuesta, exitoso=True)

    except Exception as e:
        # Log del error (aquí iría el logging estructurado)
        print(f"Error procesando consulta: {e}")

        # Devolver un error HTTP genérico (sin exponer detalles internos)
        raise HTTPException(
            status_code=500,
            detail=f"Error al procesar la consulta: {str(e)}",
        )


@app.post("/chat", tags=["Agente"])
async def chat(request: ConsultaRequest):
    """
    Endpoint de chat para mantener una conversación continua.

    Es lo mismo que /consulta pero devuelve una estructura más simple.
    La sesión del agente mantiene el historial de la conversación.

    Args:
        request: objeto con el campo 'pregunta'

    Returns:
        JSON con la respuesta del agente
    """
    return await consulta(request)


@app.get("/metricas", tags=["Observabilidad"])
async def metricas():
    """
    Métricas agregadas de las interacciones registradas (Fase 6).

    Es una vista de OPERADOR (dueño/equipo del negocio), no del cliente: la
    consume el panel en app/dashboard.py, separado del chat.
    """
    sesion = obtener_sesion()
    try:
        return calcular_metricas(sesion)
    finally:
        sesion.close()


@app.post("/reiniciar", tags=["Agente"])
async def reiniciar():
    """
    Descarta la conversación actual y arranca una nueva.

    El agente vive como una única instancia global (para conservar el
    historial entre mensajes), así que "reiniciar" es descartarla: la
    próxima consulta crea una instancia fresca, sin historial ni contexto
    de tools de la conversación anterior.
    """
    global _agente
    _agente = None
    return {"reiniciado": True}


# Manejo de errores global
@app.exception_handler(Exception)
async def manejar_excepcion(request, exc):
    """Captura excepciones no manejadas y devuelve un error 500."""
    return {"error": f"Error interno: {str(exc)}"}


if __name__ == "__main__":
    # Para desarrollo
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info",
    )
