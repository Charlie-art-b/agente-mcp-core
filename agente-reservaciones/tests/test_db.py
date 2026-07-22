"""
Tests de la capa de datos
==========================
Prueban los modelos y las relaciones entre tablas usando SQLite en
memoria -- no necesitan Postgres corriendo.
"""

from datetime import date

import pytest

from app.db.models import (
    Cliente,
    HorarioDisponible,
    Reservacion,
    Servicio,
    TicketEscalado,
)
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas


@pytest.fixture
def sesion():
    """Sesión nueva contra una base SQLite en memoria, limpia en cada test."""
    engine = crear_engine("sqlite:///:memory:")
    crear_tablas(engine)
    fabrica = crear_fabrica_sesiones(engine)
    s = fabrica()
    yield s
    s.close()


def test_crear_cliente(sesion):
    cliente = Cliente(nombre="Ana Pérez", telefono="8888-0001")
    sesion.add(cliente)
    sesion.commit()

    encontrado = sesion.query(Cliente).filter_by(telefono="8888-0001").first()
    assert encontrado is not None
    assert encontrado.nombre == "Ana Pérez"


def test_telefono_de_cliente_es_unico(sesion):
    sesion.add(Cliente(nombre="Ana", telefono="8888-0001"))
    sesion.commit()

    sesion.add(Cliente(nombre="Otra Ana", telefono="8888-0001"))
    with pytest.raises(Exception):
        sesion.commit()


def test_crear_servicio_y_horario(sesion):
    servicio = Servicio(nombre="Corte de cabello", duracion_minutos=30, precio=8000)
    sesion.add(servicio)
    sesion.flush()

    horario = HorarioDisponible(
        servicio_id=servicio.id,
        fecha=date(2026, 8, 1),
        hora_inicio="09:00",
        hora_fin="09:30",
        disponible=True,
    )
    sesion.add(horario)
    sesion.commit()

    assert horario.servicio.nombre == "Corte de cabello"
    assert servicio.horarios[0].hora_inicio == "09:00"


def test_reservacion_conecta_cliente_servicio_y_horario(sesion):
    cliente = Cliente(nombre="Luis", telefono="8888-0002")
    servicio = Servicio(nombre="Manicure", duracion_minutos=45, precio=12000)
    sesion.add_all([cliente, servicio])
    sesion.flush()

    horario = HorarioDisponible(
        servicio_id=servicio.id,
        fecha=date(2026, 8, 1),
        hora_inicio="11:00",
        hora_fin="11:45",
        disponible=True,
    )
    sesion.add(horario)
    sesion.flush()

    reservacion = Reservacion(
        cliente_id=cliente.id,
        servicio_id=servicio.id,
        horario_id=horario.id,
    )
    sesion.add(reservacion)
    sesion.commit()

    assert reservacion.estado == "confirmada"  # valor por defecto
    assert reservacion.cliente.nombre == "Luis"
    assert reservacion.horario.hora_inicio == "11:00"
    assert cliente.reservaciones[0].id == reservacion.id


def test_ticket_escalado_por_defecto_queda_abierto(sesion):
    cliente = Cliente(nombre="Ana", telefono="8888-0003")
    sesion.add(cliente)
    sesion.flush()

    ticket = TicketEscalado(cliente_id=cliente.id, motivo="Reclamo por cobro duplicado")
    sesion.add(ticket)
    sesion.commit()

    assert ticket.estado == "abierto"
    assert cliente.tickets[0].motivo == "Reclamo por cobro duplicado"