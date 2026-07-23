"""
Tests de la tool escalar_caso
==============================
Prueban la tool aislada contra SQLite en memoria.

Buena parte de los casos son de validación: esta tool la invoca un modelo,
no un formulario, así que puede llegar con el motivo vacío o solo con
espacios si el usuario dijo apenas "quiero hablar con alguien". Un ticket
sin motivo no le sirve a quien lo tenga que atender.
"""

import pytest

from app.db.models import Cliente, TicketEscalado
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas
from app.tools.escalar_caso import escalar_caso


@pytest.fixture
def sesion():
    """Base SQLite en memoria, vacía."""
    engine = crear_engine("sqlite:///:memory:")
    crear_tablas(engine)
    s = crear_fabrica_sesiones(engine)()
    yield s
    s.close()


# --- Camino feliz ---


def test_crea_el_ticket_y_devuelve_su_numero(sesion):
    resultado = escalar_caso(
        motivo="Le cobraron dos veces el mismo servicio",
        nombre_cliente="Ana Pérez",
        telefono="8888-0001",
        sesion=sesion,
    )

    assert resultado["escalado"] is True
    assert isinstance(resultado["ticket_id"], int)
    assert resultado["estado"] == "abierto"


def test_el_ticket_queda_persistido(sesion):
    resultado = escalar_caso(
        motivo="Quiere cancelar sin costo fuera del plazo de 24 horas",
        nombre_cliente="Luis",
        telefono="8888-0002",
        sesion=sesion,
    )

    guardado = sesion.get(TicketEscalado, resultado["ticket_id"])
    assert guardado is not None
    assert guardado.estado == "abierto"
    assert "24 horas" in guardado.motivo


def test_devuelve_un_mensaje_listo_para_el_usuario(sesion):
    """El agente necesita algo concreto que decirle a la persona."""
    resultado = escalar_caso(
        motivo="Reclamo por el servicio recibido",
        nombre_cliente="Ana",
        telefono="8888-0001",
        sesion=sesion,
    )

    mensaje = resultado["mensaje_para_el_usuario"]
    assert str(resultado["ticket_id"]) in mensaje


def test_el_motivo_se_guarda_completo_y_no_resumido(sesion):
    """Quien lea el ticket después no ve la conversación original."""
    motivo = (
        "El cliente reservó un corte para el jueves, llegó y le dijeron que "
        "no había nadie. Quiere que le reprogramen sin costo y una explicación."
    )
    resultado = escalar_caso(
        motivo=motivo, nombre_cliente="Ana", telefono="8888-0001", sesion=sesion
    )

    assert sesion.get(TicketEscalado, resultado["ticket_id"]).motivo == motivo


# --- Manejo del cliente ---


def test_crea_el_cliente_si_es_la_primera_vez(sesion):
    escalar_caso(
        motivo="Consulta que el agente no pudo resolver",
        nombre_cliente="Cliente Nuevo",
        telefono="8888-9999",
        sesion=sesion,
    )

    creado = sesion.query(Cliente).filter_by(telefono="8888-9999").first()
    assert creado is not None
    assert creado.nombre == "Cliente Nuevo"


def test_reutiliza_el_cliente_existente(sesion):
    """Dos reclamos de la misma persona no deben duplicar su ficha."""
    sesion.add(Cliente(nombre="Ana Pérez", telefono="8888-0001"))
    sesion.commit()

    escalar_caso(motivo="Primer reclamo", nombre_cliente="Ana", telefono="8888-0001", sesion=sesion)
    escalar_caso(motivo="Segundo reclamo", nombre_cliente="Ana", telefono="8888-0001", sesion=sesion)

    assert sesion.query(Cliente).filter_by(telefono="8888-0001").count() == 1
    assert sesion.query(TicketEscalado).count() == 2


def test_se_puede_escalar_sin_telefono(sesion):
    resultado = escalar_caso(
        motivo="No dejó datos de contacto", nombre_cliente="Anónimo", sesion=sesion
    )

    assert resultado["escalado"] is True


# --- Validación (la tool la llama un modelo, no un formulario) ---


def test_motivo_vacio_se_rechaza(sesion):
    resultado = escalar_caso(motivo="", nombre_cliente="Ana", sesion=sesion)

    assert resultado["escalado"] is False
    assert "motivo" in resultado["error"].lower()
    assert sesion.query(TicketEscalado).count() == 0


def test_motivo_de_solo_espacios_se_rechaza(sesion):
    resultado = escalar_caso(motivo="    ", nombre_cliente="Ana", sesion=sesion)

    assert resultado["escalado"] is False
    assert sesion.query(TicketEscalado).count() == 0


def test_nombre_vacio_se_rechaza(sesion):
    resultado = escalar_caso(motivo="Un reclamo real", nombre_cliente="", sesion=sesion)

    assert resultado["escalado"] is False
    assert sesion.query(TicketEscalado).count() == 0


def test_un_rechazo_no_deja_cliente_creado(sesion):
    """La validación corre antes de tocar la base."""
    escalar_caso(motivo="", nombre_cliente="Ana", telefono="8888-0001", sesion=sesion)

    assert sesion.query(Cliente).count() == 0
