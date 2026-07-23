"""
Tool: consultar_disponibilidad
===============================
Consulta los horarios libres del negocio en una fecha dada. Es la tool
de solo lectura sobre Postgres: no modifica nada, así que el agente la
puede llamar libremente para responder "¿tenés campo mañana?".

Devuelve el `horario_id` de cada espacio libre a propósito: es el dato
que `crear_reservacion` necesita después, y así el agente puede encadenar
las dos tools sin tener que adivinar a qué horario se refiere el usuario.
"""

from datetime import date

from app.db.models import HorarioDisponible, Servicio
from app.db.session import obtener_sesion


def consultar_disponibilidad(
    fecha: str,
    servicio: str | None = None,
    sesion=None,
) -> dict:
    """
    Consulta qué horarios están disponibles para reservar en una fecha.

    Úsala cuando el usuario pregunte si hay campo, cupo o espacio libre,
    o cuando quiera agendar algo y haya que confirmar la disponibilidad
    antes de crear la reservación.

    Args:
        fecha: la fecha a consultar en formato YYYY-MM-DD (ej. "2026-08-01").
        servicio: nombre del servicio a filtrar (ej. "corte"). Si se omite,
            devuelve los horarios libres de todos los servicios. No hace
            falta el nombre exacto: busca por coincidencia parcial.

    Returns:
        dict con la lista de horarios disponibles. Cada uno incluye su
        `horario_id` (necesario para crear la reservación), la hora de
        inicio y fin, el servicio, su precio y su duración.
    """
    # `sesion` se puede inyectar desde los tests (igual que se hace con la
    # URL en crear_engine); en uso normal se abre y se cierra acá.
    sesion_propia = sesion is None
    if sesion_propia:
        sesion = obtener_sesion()

    try:
        try:
            fecha_obj = date.fromisoformat(fecha)
        except ValueError:
            return {
                "disponibles": [],
                "error": f"La fecha '{fecha}' no tiene un formato válido. "
                "Se espera YYYY-MM-DD, por ejemplo 2026-08-01.",
            }

        consulta = (
            sesion.query(HorarioDisponible)
            .join(Servicio)
            .filter(
                HorarioDisponible.fecha == fecha_obj,
                HorarioDisponible.disponible.is_(True),
            )
        )

        if servicio:
            # Coincidencia parcial e insensible a mayúsculas: el agente
            # suele mandar "corte" cuando en la base dice "Corte de cabello".
            consulta = consulta.filter(Servicio.nombre.ilike(f"%{servicio}%"))

            # Distinguir "ese servicio no existe" de "existe pero está lleno"
            # le permite al agente dar una respuesta útil en vez de un
            # "no hay nada" genérico.
            existe = (
                sesion.query(Servicio)
                .filter(Servicio.nombre.ilike(f"%{servicio}%"))
                .first()
            )
            if existe is None:
                nombres = [n for (n,) in sesion.query(Servicio.nombre).all()]
                return {
                    "disponibles": [],
                    "error": f"No existe ningún servicio que coincida con "
                    f"'{servicio}'.",
                    "servicios_disponibles": nombres,
                }

        horarios = consulta.order_by(HorarioDisponible.hora_inicio).all()

        disponibles = [
            {
                "horario_id": h.id,
                "hora_inicio": h.hora_inicio,
                "hora_fin": h.hora_fin,
                "servicio": h.servicio.nombre,
                "servicio_id": h.servicio_id,
                # precio es Numeric en la base -> Decimal en Python, que no
                # es serializable a JSON. Se convierte acá porque esta
                # respuesta viaja al modelo como JSON vía MCP.
                "precio": float(h.servicio.precio),
                "duracion_minutos": h.servicio.duracion_minutos,
            }
            for h in horarios
        ]

        return {
            "fecha": fecha,
            "servicio_consultado": servicio,
            "disponibles": disponibles,
            "total": len(disponibles),
        }

    finally:
        if sesion_propia:
            sesion.close()