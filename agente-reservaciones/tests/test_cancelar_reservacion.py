"""
Tests de la tool cancelar_reservacion
======================================
Prueban la tool aislada contra SQLite en memoria. Además del camino feliz,
cubren lo que hace distinta a una tool que revierte una escritura:

  - que el horario vuelva efectivamente al pool de disponibles,
  - que cancelar dos veces no libere el horario dos veces,
  - que si algo falla a mitad de camino no quede una reserva cancelada
    con su horario todavía ocupado.

También cubren el paso previo (buscar por teléfono), que existe para no
cancelar la cita equivocada cuando alguien tiene varias.
"""

from datetime import date, timedelta

import pytest

from app.db.models import HorarioDisponible, Reservacion, Servicio
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas
from app.tools.cancelar_reservacion import cancelar_reservacion
from app.tools.consultar_disponibilidad import consultar_disponibilidad
from app.tools.crear_reservacion import crear_reservacion

# Lejos en el futuro: siempre a más de 24 horas, así el aviso de
# penalización es determinístico corra el test a la hora que corra.
FECHA_LEJANA = date.today() + timedelta(days=10)
FECHA_LEJANA_STR = FECHA_LEJANA.isoformat()

# Hoy a las 00:00 ya pasó (o es este mismo instante): siempre a menos de
# 24 horas de anticipación.
FECHA_HOY = date.today()

TELEFONO = "8888-0001"


@pytest.fixture
def sesion():
    """
    Base en memoria con un servicio, tres horarios lejanos y uno para hoy.

    Los horarios 1..3 son del día lejano; el 4 es de hoy a las 00:00 y se
    usa solo para el aviso de penalización.
    """
    engine = crear_engine("sqlite:///:memory:")
    crear_tablas(engine)
    s = crear_fabrica_sesiones(engine)()

    corte = Servicio(nombre="Corte de cabello", duracion_minutos=30, precio=8000)
    s.add(corte)
    s.flush()

    s.add_all(
        [
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=FECHA_LEJANA,
                hora_inicio="09:00",
                hora_fin="09:30",
                disponible=True,
            ),
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=FECHA_LEJANA,
                hora_inicio="10:00",
                hora_fin="10:30",
                disponible=True,
            ),
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=FECHA_LEJANA,
                hora_inicio="11:00",
                hora_fin="11:30",
                disponible=True,
            ),
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=FECHA_HOY,
                hora_inicio="00:00",
                hora_fin="00:30",
                disponible=True,
            ),
        ]
    )
    s.commit()

    yield s
    s.close()


@pytest.fixture
def reserva(sesion):
    """Una reservación confirmada sobre el horario 1, lista para cancelar."""
    return crear_reservacion(1, "Ana Pérez", telefono=TELEFONO, sesion=sesion)


# --- Camino feliz ---


def test_cancela_y_devuelve_los_datos_de_la_cita(sesion, reserva):
    resultado = cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)

    assert resultado["cancelada"] is True
    assert resultado["estado"] == "cancelada"
    assert resultado["servicio"] == "Corte de cabello"
    assert resultado["fecha"] == FECHA_LEJANA_STR
    assert resultado["hora_inicio"] == "09:00"


def test_la_reservacion_queda_cancelada_en_la_base(sesion, reserva):
    cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)

    guardada = sesion.get(Reservacion, reserva["reservacion_id"])
    assert guardada.estado == "cancelada"


def test_el_horario_vuelve_a_estar_disponible(sesion, reserva):
    assert sesion.get(HorarioDisponible, 1).disponible is False

    cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)

    assert sesion.get(HorarioDisponible, 1).disponible is True


def test_el_horario_cancelado_se_vuelve_a_ofrecer(sesion, reserva):
    """El efecto que ve el usuario: el espacio queda libre para otra persona."""
    ocupado = consultar_disponibilidad(FECHA_LEJANA_STR, sesion=sesion)
    cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)
    liberado = consultar_disponibilidad(FECHA_LEJANA_STR, sesion=sesion)

    assert liberado["total"] == ocupado["total"] + 1
    assert 1 in [h["horario_id"] for h in liberado["disponibles"]]


def test_otra_persona_puede_tomar_el_horario_liberado(sesion, reserva):
    """La cancelación no sirve de nada si el horario no se puede volver a vender."""
    cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)

    nueva = crear_reservacion(1, "Luis Gómez", telefono="8888-0002", sesion=sesion)

    assert nueva["creada"] is True
    assert nueva["hora_inicio"] == "09:00"


# --- Aviso de penalización ---


def test_cancelar_con_mucha_anticipacion_no_avisa_de_cargo(sesion, reserva):
    resultado = cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)

    assert resultado["penalizacion_posible"] is False


def test_cancelar_sobre_la_hora_avisa_del_posible_cargo(sesion):
    """
    La tool no bloquea la cancelación tardía (eso lo decide el negocio),
    pero tiene que avisar para que el agente no sorprenda al cliente.
    """
    tardia = crear_reservacion(4, "Ana", telefono=TELEFONO, sesion=sesion)

    resultado = cancelar_reservacion(tardia["reservacion_id"], sesion=sesion)

    assert resultado["cancelada"] is True
    assert resultado["penalizacion_posible"] is True
    assert "24 horas" in resultado["detalle_penalizacion"]


# --- Paso previo: buscar por teléfono ---


def test_con_solo_el_telefono_devuelve_las_reservas_sin_cancelar(sesion, reserva):
    resultado = cancelar_reservacion(telefono=TELEFONO, sesion=sesion)

    assert resultado["cancelada"] is False
    assert resultado["requiere_confirmacion"] is True
    assert len(resultado["reservaciones_activas"]) == 1
    assert resultado["reservaciones_activas"][0]["reservacion_id"] == (
        reserva["reservacion_id"]
    )
    # Y nada se tocó: la reserva sigue viva.
    assert sesion.get(Reservacion, reserva["reservacion_id"]).estado == "confirmada"
    assert sesion.get(HorarioDisponible, 1).disponible is False


def test_lista_varias_reservas_de_la_mas_proxima_a_la_mas_lejana(sesion):
    """Es el caso que motiva el paso previo: hay que saber cuál cancelar."""
    crear_reservacion(2, "Ana", telefono=TELEFONO, sesion=sesion)
    crear_reservacion(1, "Ana", telefono=TELEFONO, sesion=sesion)

    resultado = cancelar_reservacion(telefono=TELEFONO, sesion=sesion)

    horas = [r["hora_inicio"] for r in resultado["reservaciones_activas"]]
    assert horas == ["09:00", "10:00"]


def test_no_lista_las_reservas_ya_canceladas(sesion, reserva):
    cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)

    resultado = cancelar_reservacion(telefono=TELEFONO, sesion=sesion)

    assert resultado["cancelada"] is False
    assert "No encontré reservaciones activas" in resultado["error"]


def test_telefono_sin_reservas_devuelve_error_claro(sesion):
    resultado = cancelar_reservacion(telefono="8888-9999", sesion=sesion)

    assert resultado["cancelada"] is False
    assert "8888-9999" in resultado["error"]


def test_no_confunde_las_reservas_de_otra_persona(sesion, reserva):
    crear_reservacion(2, "Luis", telefono="8888-0002", sesion=sesion)

    resultado = cancelar_reservacion(telefono=TELEFONO, sesion=sesion)

    ids = [r["reservacion_id"] for r in resultado["reservaciones_activas"]]
    assert ids == [reserva["reservacion_id"]]


# --- Errores y concurrencia ---


def test_sin_id_ni_telefono_pide_el_dato(sesion):
    """El modelo puede llamar la tool con las manos vacías ante un 'cancelá lo mío'."""
    resultado = cancelar_reservacion(sesion=sesion)

    assert resultado["cancelada"] is False
    assert "número de reservación" in resultado["error"]


def test_telefono_en_blanco_no_cuenta_como_telefono(sesion):
    resultado = cancelar_reservacion(telefono="   ", sesion=sesion)

    assert resultado["cancelada"] is False
    assert "número de reservación" in resultado["error"]


def test_reservacion_inexistente_devuelve_error_claro(sesion):
    resultado = cancelar_reservacion(999, sesion=sesion)

    assert resultado["cancelada"] is False
    assert "999" in resultado["error"]


def test_cancelar_dos_veces_la_misma_reserva_rebota(sesion, reserva):
    """
    El caso que motiva el UPDATE atómico: la segunda pasada no debe volver
    a liberar el horario, porque para entonces puede ser de otra persona.
    """
    primera = cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)
    otra = crear_reservacion(1, "Luis", telefono="8888-0002", sesion=sesion)
    segunda = cancelar_reservacion(reserva["reservacion_id"], sesion=sesion)

    assert primera["cancelada"] is True
    assert otra["creada"] is True
    assert segunda["cancelada"] is False
    assert "no está activa" in segunda["error"]

    # Lo importante: la reserva NUEVA sigue en pie con su horario ocupado.
    assert sesion.get(HorarioDisponible, 1).disponible is False
    assert sesion.get(Reservacion, otra["reservacion_id"]).estado == "confirmada"


def test_un_fallo_a_mitad_de_camino_no_deja_la_reserva_a_medio_cancelar(
    sesion, monkeypatch
):
    """
    Lo peor que puede pasar: la reserva queda cancelada pero el horario
    sigue ocupado, bloqueado para siempre sin nada que lo justifique.
    """
    creada = crear_reservacion(1, "Ana", telefono=TELEFONO, sesion=sesion)

    def explota(*args, **kwargs):
        raise RuntimeError("fallo simulado al guardar")

    monkeypatch.setattr(sesion, "commit", explota)

    resultado = cancelar_reservacion(creada["reservacion_id"], sesion=sesion)

    assert resultado["cancelada"] is False
    assert "fallo simulado" in resultado["error"]

    monkeypatch.undo()
    assert sesion.get(Reservacion, creada["reservacion_id"]).estado == "confirmada"
    assert sesion.get(HorarioDisponible, 1).disponible is False
