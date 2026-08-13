"""
Tool: cancelar_reservacion
===========================
Cancela una reservación existente y devuelve su horario al pool de
disponibles. Es la contraparte de `crear_reservacion` y, como ella,
escribe en la base -- así que comparte sus dos cuidados:

1. La carrera por cancelar dos veces
   Si el mismo pedido de cancelación entra dos veces, el riesgo no es un
   mensaje repetido: cada pasada liberaría el horario, y entre medio otra
   persona pudo haberlo reservado de nuevo -- su reserva quedaría con el
   horario marcado como libre. Por eso el estado se reclama con un
   `UPDATE ... WHERE estado = 'confirmada'`, que la base resuelve de forma
   atómica. Si afecta 0 filas, ya estaba cancelada y no hay nada que hacer.

2. Todo o nada
   Marcar la reserva como cancelada y liberar el horario tienen que pasar
   juntos, en un solo commit. Si quedara solo lo primero, el horario
   seguiría bloqueado para siempre sin una reserva que lo justifique.

Cómo se elige QUÉ reserva cancelar:
   Cancelar es de dos pasos, igual que reservar. Nadie recuerda el número
   de su reservación, así que la tool acepta el teléfono y devuelve las
   reservas activas de esa persona (con su id) SIN cancelar nada. Recién
   con un `reservacion_id` concreto ejecuta la cancelación. Es el mismo
   encadenado que `consultar_disponibilidad` -> `crear_reservacion`, y
   evita cancelar la cita equivocada cuando alguien tiene varias.

   El teléfono es la única forma de reconocer a alguien (es la columna
   única del esquema, ver app/db/clientes.py). Quien haya reservado solo
   con correo tiene que dar su número de reservación.
"""

from datetime import datetime, time

from app.db.models import Cliente, HorarioDisponible, Reservacion
from app.db.session import obtener_sesion

ESTADO_CONFIRMADA = "confirmada"
ESTADO_CANCELADA = "cancelada"

# Anticipación mínima para cancelar sin cargo, según la política del negocio
# (ver data/documents/). La tool NO bloquea una cancelación tardía: aplicar o
# perdonar el cargo lo decide el negocio, no el agente. Solo avisa, para que
# la respuesta al cliente no lo tome por sorpresa. El monto tampoco se pone
# acá a propósito: vive en la base de conocimiento, y duplicarlo en código
# sería una segunda fuente de verdad que se desincroniza sin avisar.
HORAS_SIN_PENALIZACION = 24


def _momento_de_la_cita(horario: HorarioDisponible) -> datetime | None:
    """
    Combina `fecha` + `hora_inicio` en un datetime, o None si la hora no
    tiene el formato "HH:MM" esperado.
    """
    try:
        hora, minuto = (int(parte) for parte in horario.hora_inicio.split(":"))
        return datetime.combine(horario.fecha, time(hour=hora, minute=minuto))
    except (AttributeError, TypeError, ValueError):
        return None


def _aviso_de_penalizacion(horario: HorarioDisponible) -> dict:
    """
    Dice si esta cancelación cae dentro del plazo con cargo. Si no se puede
    calcular el momento de la cita, devuelve {} (mejor no decir nada que
    afirmar algo falso sobre un cobro).
    """
    momento = _momento_de_la_cita(horario)
    if momento is None:
        return {}

    horas_de_anticipacion = (momento - datetime.now()).total_seconds() / 3600
    if horas_de_anticipacion >= HORAS_SIN_PENALIZACION:
        return {"penalizacion_posible": False}

    return {
        "penalizacion_posible": True,
        "detalle_penalizacion": (
            f"Se está cancelando con menos de {HORAS_SIN_PENALIZACION} horas de "
            "anticipación, así que según la política del negocio puede aplicarse "
            "un cargo. Avisale al cliente; si quiere el detalle del monto, "
            "consultá la política de cancelación."
        ),
    }


def _reservaciones_activas(sesion, telefono: str) -> list[dict]:
    """
    Reservas confirmadas de la persona con ese teléfono, de la más próxima
    a la más lejana. Cada una con su `reservacion_id`, que es el dato que
    hace falta para cancelarla.
    """
    filas = (
        sesion.query(Reservacion)
        .join(Cliente, Reservacion.cliente_id == Cliente.id)
        .join(HorarioDisponible, Reservacion.horario_id == HorarioDisponible.id)
        .filter(
            Cliente.telefono == telefono,
            Reservacion.estado == ESTADO_CONFIRMADA,
        )
        .order_by(HorarioDisponible.fecha, HorarioDisponible.hora_inicio)
        .all()
    )

    return [
        {
            "reservacion_id": r.id,
            "servicio": r.servicio.nombre,
            "fecha": r.horario.fecha.isoformat(),
            "hora_inicio": r.horario.hora_inicio,
            "hora_fin": r.horario.hora_fin,
        }
        for r in filas
    ]


def cancelar_reservacion(
    reservacion_id: int | None = None,
    telefono: str | None = None,
    sesion=None,
) -> dict:
    """
    Cancela una reservación y libera su horario para que otra persona
    pueda tomarlo.

    Se usa en dos pasos. Si el cliente no sabe su número de reservación,
    llamala con su `telefono`: devuelve las reservas activas de esa
    persona sin cancelar nada, para que el cliente diga cuál. Después
    llamala de nuevo con el `reservacion_id` elegido y ahí sí se cancela.

    Args:
        reservacion_id: número de la reservación a cancelar, tal como lo
            devolvió `crear_reservacion` o la búsqueda por teléfono.
        telefono: teléfono con el que se hizo la reserva. Sirve para
            buscar las reservas activas cuando no se tiene el número.

    Returns:
        dict con el resultado. Si se canceló, incluye los datos de la cita
        y si la cancelación cae dentro del plazo con cargo. Si solo se dio
        el teléfono, incluye `reservaciones_activas` para elegir cuál
        cancelar (todavía sin cancelar nada).
    """
    sesion_propia = sesion is None
    if sesion_propia:
        sesion = obtener_sesion()

    try:
        # --- Paso 1: sin número, buscar por teléfono y devolver opciones ---
        if reservacion_id is None:
            if not telefono or not telefono.strip():
                return {
                    "cancelada": False,
                    "error": "Necesito el número de reservación, o el teléfono "
                    "con el que se hizo la reserva, para saber qué cancelar.",
                }

            activas = _reservaciones_activas(sesion, telefono.strip())
            if not activas:
                return {
                    "cancelada": False,
                    "error": f"No encontré reservaciones activas para el teléfono "
                    f"{telefono.strip()}. Puede que la reserva se haya hecho con "
                    "otro número o solo con correo: en ese caso hace falta el "
                    "número de reservación.",
                }

            return {
                "cancelada": False,
                "requiere_confirmacion": True,
                "reservaciones_activas": activas,
                "mensaje_para_el_agente": (
                    "Todavía no cancelé nada. Mostrale estas reservas al cliente, "
                    "preguntale cuál quiere cancelar, y volvé a llamar esta tool "
                    "con el reservacion_id que elija."
                ),
            }

        # --- Paso 2: cancelar la reservación indicada ---
        reservacion = sesion.get(Reservacion, reservacion_id)
        if reservacion is None:
            return {
                "cancelada": False,
                "error": f"No existe ninguna reservación con el número "
                f"{reservacion_id}. Verificá el número con el cliente, o buscá "
                "sus reservas por teléfono.",
            }

        # El estado se reclama dentro del UPDATE a propósito: si se leyera
        # primero y se escribiera después, dos cancelaciones simultáneas
        # podrían ambas creerse la que canceló y liberar el horario dos veces.
        filas_afectadas = (
            sesion.query(Reservacion)
            .filter(
                Reservacion.id == reservacion_id,
                Reservacion.estado == ESTADO_CONFIRMADA,
            )
            .update({"estado": ESTADO_CANCELADA}, synchronize_session=False)
        )

        if filas_afectadas == 0:
            sesion.rollback()
            return {
                "cancelada": False,
                "error": f"La reservación {reservacion_id} no está activa: su "
                f"estado es '{reservacion.estado}'. No hay nada que cancelar.",
            }

        horario = reservacion.horario

        # Devolver el horario al pool. Va en el mismo commit que el cambio de
        # estado: o pasan las dos cosas, o no pasa ninguna.
        sesion.query(HorarioDisponible).filter(
            HorarioDisponible.id == reservacion.horario_id
        ).update({"disponible": True}, synchronize_session=False)

        sesion.commit()

        return {
            "cancelada": True,
            "reservacion_id": reservacion.id,
            # No se lee de `reservacion.estado`: el UPDATE con
            # synchronize_session=False no refresca el objeto en memoria, que
            # sigue diciendo "confirmada".
            "estado": ESTADO_CANCELADA,
            "servicio": horario.servicio.nombre,
            "fecha": horario.fecha.isoformat(),
            "hora_inicio": horario.hora_inicio,
            "hora_fin": horario.hora_fin,
            "horario_liberado": True,
            **_aviso_de_penalizacion(horario),
        }

    except Exception as exc:
        # Si algo falla después de haber marcado la reserva como cancelada,
        # el rollback la devuelve a confirmada con su horario ocupado.
        sesion.rollback()
        return {
            "cancelada": False,
            "error": f"No se pudo cancelar la reservación: {exc}",
        }

    finally:
        if sesion_propia:
            sesion.close()
