"""
Tool: escalar_caso
===================
Abre un ticket para que una persona del negocio retome el caso.

Es la válvula de escape del agente. Sin ella, ante algo que no puede
resolver -- un reclamo, una excepción a la política, un pedido que
ninguna otra tool cubre -- solo le queda improvisar una respuesta o
repetir que no puede ayudar. Ninguna de las dos es aceptable cuando del
otro lado hay un cliente real.

El ticket queda `abierto` y con el motivo en las palabras del usuario, no
resumido por el agente: quien lo lea después necesita el contexto
original para saber qué pasó.
"""

from app.db.clientes import buscar_o_crear_cliente
from app.db.models import TicketEscalado
from app.db.session import obtener_sesion


def escalar_caso(
    motivo: str,
    nombre_cliente: str,
    telefono: str | None = None,
    email: str | None = None,
    sesion=None,
) -> dict:
    """
    Registra un caso para que lo atienda una persona del negocio.

    Úsala cuando no puedas resolver lo que el usuario necesita con las
    otras tools: un reclamo o queja, un pedido de excepción a las
    políticas (cancelar sin costo fuera de plazo, un descuento), algo que
    la base de conocimiento no cubre, o cuando el usuario pida
    explícitamente hablar con una persona.

    No la uses para preguntas que `buscar_conocimiento` puede responder,
    ni para reservar (eso es `crear_reservacion`). Escalar innecesariamente
    le genera trabajo al negocio y demora al usuario.

    Al usarla, avisale al usuario que su caso quedó registrado y que
    alguien lo va a contactar.

    Args:
        motivo: qué necesita el usuario y por qué no se pudo resolver.
            Escribilo con el detalle suficiente para que quien lo lea
            después entienda el caso sin ver la conversación.
        nombre_cliente: nombre de la persona.
        telefono: teléfono de contacto. Sin esto el negocio no tiene cómo
            responderle, así que pedilo si no lo tenés.
        email: correo de contacto (opcional).

    Returns:
        dict con el número de ticket y su estado, para poder dárselo al
        usuario como referencia.
    """
    sesion_propia = sesion is None
    if sesion_propia:
        sesion = obtener_sesion()

    try:
        # El modelo podría llamar a la tool con un motivo vacío si el
        # usuario solo dijo "quiero hablar con alguien". Un ticket sin
        # motivo no le sirve a quien lo tenga que atender.
        if not motivo or not motivo.strip():
            return {
                "escalado": False,
                "error": "Hace falta un motivo. Explicá qué necesita el "
                "usuario y por qué no se pudo resolver.",
            }

        if not nombre_cliente or not nombre_cliente.strip():
            return {
                "escalado": False,
                "error": "Hace falta el nombre del cliente para poder "
                "registrar el caso.",
            }

        cliente = buscar_o_crear_cliente(sesion, nombre_cliente.strip(), telefono, email)

        ticket = TicketEscalado(cliente_id=cliente.id, motivo=motivo.strip())
        sesion.add(ticket)
        sesion.commit()

        return {
            "escalado": True,
            "ticket_id": ticket.id,
            "estado": ticket.estado,
            "motivo": ticket.motivo,
            "cliente": {
                "id": cliente.id,
                "nombre": cliente.nombre,
                "telefono": cliente.telefono,
            },
            "mensaje_para_el_usuario": (
                f"Tu caso quedó registrado con el número {ticket.id}. "
                "Alguien del equipo te va a contactar."
            ),
        }

    except Exception as exc:
        sesion.rollback()
        return {
            "escalado": False,
            "error": f"No se pudo registrar el caso: {exc}",
        }

    finally:
        if sesion_propia:
            sesion.close()
