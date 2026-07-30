"""
Tool: crear_reservacion
========================
Agenda un horario a nombre de un cliente. Es la primera tool que ESCRIBE
en la base, y por eso tiene dos cuidados que las de solo lectura no
necesitan.

1. La carrera por el horario
   Consultar disponibilidad y reservar son dos momentos distintos: entre
   que el agente ve un horario libre y lo reserva, otra persona pudo
   haberlo tomado. Por eso acá NO se confía en lo que devolvió
   `consultar_disponibilidad` -- el horario se reclama con un
   `UPDATE ... WHERE disponible = true`, que la base resuelve de forma
   atómica. Si afecta 0 filas, alguien más llegó primero.

2. Todo o nada
   Marcar el horario como ocupado y crear la reservación tienen que pasar
   juntos. Si se hiciera en dos commits y el segundo fallara, quedaría un
   horario bloqueado sin reservación que lo justifique -- imposible de
   detectar después salvo auditando a mano.
"""

from app.db.clientes import buscar_o_crear_cliente
from app.db.models import HorarioDisponible, Reservacion
from app.db.session import obtener_sesion


def _horarios_alternativos(sesion, horario: HorarioDisponible) -> list[dict]:
    """Otros horarios libres del mismo servicio y día, para poder ofrecer algo."""
    otros = (
        sesion.query(HorarioDisponible)
        .filter(
            HorarioDisponible.servicio_id == horario.servicio_id,
            HorarioDisponible.fecha == horario.fecha,
            HorarioDisponible.disponible.is_(True),
            HorarioDisponible.id != horario.id,
        )
        .order_by(HorarioDisponible.hora_inicio)
        .all()
    )
    return [
        {"horario_id": h.id, "hora_inicio": h.hora_inicio, "hora_fin": h.hora_fin}
        for h in otros
    ]


def crear_reservacion(
    horario_id: int,
    nombre_cliente: str,
    telefono: str | None = None,
    email: str | None = None,
    sesion=None,
) -> dict:
    """
    Crea una reservación para un horario disponible.

    Úsala cuando el usuario confirme que quiere agendar. Antes de llamarla
    necesitás el `horario_id`, que devuelve `consultar_disponibilidad`.
    Nunca inventes un horario_id ni asumas que un horario sigue libre: esta
    tool lo verifica y avisa si ya se ocupó.

    Args:
        horario_id: id del horario a reservar, tal como lo devolvió
            `consultar_disponibilidad`.
        nombre_cliente: nombre de la persona que reserva.
        telefono: teléfono del cliente. Si ya reservó antes con ese mismo
            número, se reutiliza su ficha en vez de duplicarla.
        email: correo del cliente. Podés dar teléfono, correo, o los dos.

    Returns:
        dict con los datos de la reservación creada. Si el horario ya no
        está disponible, devuelve un error junto con los otros horarios
        libres de ese mismo servicio y día, para poder ofrecer alternativas.
    """
    # Regla de negocio: una reserva necesita al menos UN dato de contacto
    # (teléfono o correo) para poder confirmarla y avisar al cliente. El
    # cliente elige cuál dar. Se valida antes de tocar la base para no
    # bloquear un horario por un pedido incompleto.
    tiene_telefono = bool(telefono and telefono.strip())
    tiene_email = bool(email and email.strip())
    if not tiene_telefono and not tiene_email:
        return {
            "creada": False,
            "error": "Para confirmar la reserva necesito al menos un dato de "
            "contacto: un teléfono o un correo. Pedile al cliente el que "
            "prefiera dar.",
        }

    sesion_propia = sesion is None
    if sesion_propia:
        sesion = obtener_sesion()

    try:
        horario = sesion.get(HorarioDisponible, horario_id)
        if horario is None:
            return {
                "creada": False,
                "error": f"No existe ningún horario con id {horario_id}. "
                "Consultá la disponibilidad para obtener un id válido.",
            }

        # Reclamo del horario: el filtro por `disponible` va dentro del
        # UPDATE a propósito. Si se leyera primero y se escribiera después,
        # dos reservaciones simultáneas podrían ver el mismo horario libre
        # y ambas creerse dueñas.
        filas_afectadas = (
            sesion.query(HorarioDisponible)
            .filter(
                HorarioDisponible.id == horario_id,
                HorarioDisponible.disponible.is_(True),
            )
            .update({"disponible": False}, synchronize_session=False)
        )

        if filas_afectadas == 0:
            sesion.rollback()
            return {
                "creada": False,
                "error": f"El horario de las {horario.hora_inicio} ya fue "
                "reservado por otra persona.",
                "alternativas": _horarios_alternativos(sesion, horario),
            }

        cliente = buscar_o_crear_cliente(sesion, nombre_cliente, telefono, email)

        reservacion = Reservacion(
            cliente_id=cliente.id,
            servicio_id=horario.servicio_id,
            horario_id=horario.id,
        )
        sesion.add(reservacion)

        # Un solo commit para el horario ocupado y la reservación: o quedan
        # las dos cosas, o no queda ninguna.
        sesion.commit()

        return {
            "creada": True,
            "reservacion_id": reservacion.id,
            "estado": reservacion.estado,
            "cliente": {"id": cliente.id, "nombre": cliente.nombre},
            "servicio": horario.servicio.nombre,
            "fecha": horario.fecha.isoformat(),
            "hora_inicio": horario.hora_inicio,
            "hora_fin": horario.hora_fin,
            "precio": float(horario.servicio.precio),
        }

    except Exception as exc:
        # Si algo falla después de haber marcado el horario como ocupado,
        # el rollback lo devuelve a disponible.
        sesion.rollback()
        return {
            "creada": False,
            "error": f"No se pudo crear la reservación: {exc}",
        }

    finally:
        if sesion_propia:
            sesion.close()
