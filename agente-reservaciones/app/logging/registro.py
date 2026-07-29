"""
Logging de interacciones
========================
Persiste en la tabla `interacciones_log` lo que pasó en cada turno del
agente: la pregunta, las tools que ejecutó (con su input y output), la
respuesta, los tokens, el costo y la latencia.

La tabla existe desde la Fase 2 (ver app/db/models.py). El agente arma el
registro de cada turno en `self.ultimo_registro`; acá lo guardamos.

Diseño: el agente NO escribe en la base por su cuenta. Esta función la
llama el que quiera registrar (la API, en app/main.py), y está pensada
para usarse de forma "best effort": si falla, no debe tumbar la respuesta
al usuario (ver cómo la llama app/main.py).
"""

from app.db.models import InteraccionLog
from app.db.session import obtener_sesion
from app.precios import costo_de_tokens


def registrar_interaccion(registro: dict, cliente_id: int | None = None, sesion=None) -> int | None:
    """
    Guarda un registro de interacción en la base y devuelve su id.

    Args:
        registro: el dict que arma el agente en `self.ultimo_registro`.
        cliente_id: id del cliente si se conoce (opcional; hoy queda en None,
            porque el agente no expone a qué cliente de la base corresponde
            la conversación).
        sesion: sesión de SQLAlchemy inyectable para tests; si no se pasa,
            se abre y se cierra una acá.

    Returns:
        El id de la fila creada, o None si el registro estaba vacío.
    """
    if not registro or not registro.get("mensaje_usuario"):
        return None

    tools = registro.get("tools", [])
    nombres = ",".join(t["nombre"] for t in tools)

    tokens_entrada = registro.get("tokens_entrada", 0)
    tokens_salida = registro.get("tokens_salida", 0)

    sesion_propia = sesion is None
    if sesion_propia:
        sesion = obtener_sesion()

    try:
        log = InteraccionLog(
            cliente_id=cliente_id,
            mensaje_usuario=registro["mensaje_usuario"],
            # Nombres separados por coma cuando el turno usó varias tools;
            # None cuando no usó ninguna.
            tool_llamada=nombres or None,
            tool_input=[t["input"] for t in tools] or None,
            tool_output=[t["output"] for t in tools] or None,
            respuesta_agente=registro.get("respuesta_agente"),
            tokens_input=tokens_entrada,
            tokens_output=tokens_salida,
            costo_usd=costo_de_tokens(tokens_entrada, tokens_salida),
            latencia_ms=registro.get("latencia_ms"),
        )
        sesion.add(log)
        sesion.commit()
        return log.id
    finally:
        if sesion_propia:
            sesion.close()
