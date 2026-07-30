"""
Tests de la tool crear_reservacion
===================================
Prueban la tool aislada contra SQLite en memoria. Además de los casos
normales, cubren lo que hace distinta a una tool que escribe:

  - que el horario quede efectivamente ocupado,
  - que dos reservaciones del mismo horario no puedan convivir,
  - que si algo falla a mitad de camino no quede un horario bloqueado
    sin reservación que lo justifique.
"""

from datetime import date

import pytest

from app.db.models import Cliente, HorarioDisponible, Reservacion, Servicio
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas
from app.tools.consultar_disponibilidad import consultar_disponibilidad
from app.tools.crear_reservacion import crear_reservacion

FECHA = date(2026, 8, 1)
FECHA_STR = "2026-08-01"


@pytest.fixture
def sesion():
    """Base SQLite en memoria con un servicio y tres horarios libres."""
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
                fecha=FECHA,
                hora_inicio="09:00",
                hora_fin="09:30",
                disponible=True,
            ),
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=FECHA,
                hora_inicio="10:00",
                hora_fin="10:30",
                disponible=True,
            ),
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=FECHA,
                hora_inicio="11:00",
                hora_fin="11:30",
                disponible=True,
            ),
        ]
    )
    s.commit()

    yield s
    s.close()


# --- Camino feliz ---


def test_crea_la_reservacion_y_devuelve_sus_datos(sesion):
    resultado = crear_reservacion(1, "Ana Pérez", telefono="8888-0001", sesion=sesion)

    assert resultado["creada"] is True
    assert resultado["cliente"]["nombre"] == "Ana Pérez"
    assert resultado["servicio"] == "Corte de cabello"
    assert resultado["hora_inicio"] == "09:00"
    assert resultado["fecha"] == FECHA_STR
    assert isinstance(resultado["reservacion_id"], int)


def test_la_reservacion_queda_persistida_en_la_base(sesion):
    resultado = crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)

    guardada = sesion.get(Reservacion, resultado["reservacion_id"])
    assert guardada is not None
    assert guardada.horario_id == 1
    assert guardada.estado == "confirmada"


def test_el_horario_queda_ocupado(sesion):
    crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)

    assert sesion.get(HorarioDisponible, 1).disponible is False


def test_el_horario_reservado_desaparece_de_la_disponibilidad(sesion):
    """El efecto que ve el usuario: ya no se lo ofrecen."""
    antes = consultar_disponibilidad(FECHA_STR, sesion=sesion)
    crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)
    despues = consultar_disponibilidad(FECHA_STR, sesion=sesion)

    assert despues["total"] == antes["total"] - 1
    assert 1 not in [h["horario_id"] for h in despues["disponibles"]]


def test_precio_llega_como_float_serializable(sesion):
    resultado = crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)

    assert isinstance(resultado["precio"], float)
    assert resultado["precio"] == 8000.0


# --- Manejo del cliente ---


def test_reutiliza_el_cliente_si_ya_reservo_con_el_mismo_telefono(sesion):
    """El teléfono es único: no debe duplicarse la ficha del cliente."""
    primera = crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)
    segunda = crear_reservacion(2, "Ana", telefono="8888-0001", sesion=sesion)

    assert primera["cliente"]["id"] == segunda["cliente"]["id"]
    assert sesion.query(Cliente).filter_by(telefono="8888-0001").count() == 1


def test_crea_el_cliente_si_es_la_primera_vez(sesion):
    assert sesion.query(Cliente).count() == 0

    crear_reservacion(1, "Luis Gómez", telefono="8888-0002", sesion=sesion)

    creado = sesion.query(Cliente).filter_by(telefono="8888-0002").first()
    assert creado is not None
    assert creado.nombre == "Luis Gómez"


def test_se_puede_reservar_solo_con_correo(sesion):
    """El contacto puede ser el correo: no hace falta teléfono."""
    resultado = crear_reservacion(
        1, "Ana", email="ana@example.com", sesion=sesion
    )

    assert resultado["creada"] is True
    assert resultado["cliente"]["nombre"] == "Ana"


def test_no_se_puede_reservar_sin_ningun_contacto(sesion):
    """
    Una reserva sin teléfono ni correo no sirve: no hay forma de confirmarla.
    La tool la rechaza (y no ocupa el horario) para que el agente pida el dato.
    """
    resultado = crear_reservacion(1, "Cliente sin contacto", sesion=sesion)

    assert resultado["creada"] is False
    assert "contacto" in resultado["error"]
    # No debió tocar la base: el horario sigue libre y no hay reservación.
    assert sesion.get(HorarioDisponible, 1).disponible is True
    assert sesion.query(Reservacion).count() == 0


def test_contacto_en_blanco_no_cuenta_como_contacto(sesion):
    """Un teléfono y correo vacíos equivalen a no dar contacto."""
    resultado = crear_reservacion(
        1, "Ana", telefono="   ", email="", sesion=sesion
    )

    assert resultado["creada"] is False
    assert "contacto" in resultado["error"]


# --- Errores y concurrencia ---


def test_horario_inexistente_devuelve_error_claro(sesion):
    resultado = crear_reservacion(999, "Ana", telefono="8888-0001", sesion=sesion)

    assert resultado["creada"] is False
    assert "999" in resultado["error"]
    assert sesion.query(Reservacion).count() == 0


def test_no_se_puede_reservar_dos_veces_el_mismo_horario(sesion):
    """
    El caso que motiva todo el diseño: dos personas piden las 09:00.
    La segunda tiene que rebotar, no pisar a la primera.
    """
    primera = crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)
    segunda = crear_reservacion(1, "Luis", telefono="8888-0002", sesion=sesion)

    assert primera["creada"] is True
    assert segunda["creada"] is False
    assert "ya fue reservado" in segunda["error"]

    # Y queda UNA sola reservación sobre ese horario.
    assert sesion.query(Reservacion).filter_by(horario_id=1).count() == 1


def test_al_rebotar_ofrece_los_otros_horarios_libres(sesion):
    """Sin alternativas, el agente solo puede decir 'no se pudo'."""
    crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)
    segunda = crear_reservacion(1, "Luis", telefono="8888-0002", sesion=sesion)

    horas = [a["hora_inicio"] for a in segunda["alternativas"]]
    assert horas == ["10:00", "11:00"]


def test_el_rebote_no_deja_al_cliente_a_medio_crear(sesion):
    """
    Si la reserva falla, no debe quedar una ficha de cliente huérfana
    creada durante el intento.
    """
    crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)
    crear_reservacion(1, "Luis", telefono="8888-0002", sesion=sesion)

    assert sesion.query(Cliente).filter_by(telefono="8888-0002").count() == 0


def test_un_fallo_a_mitad_de_camino_libera_el_horario(sesion, monkeypatch):
    """
    Lo peor que puede pasar: el horario queda ocupado pero la reservación
    nunca se crea. El rollback tiene que devolverlo a disponible.
    """
    def explota(*args, **kwargs):
        raise RuntimeError("fallo simulado al guardar")

    monkeypatch.setattr(sesion, "commit", explota)

    resultado = crear_reservacion(1, "Ana", telefono="8888-0001", sesion=sesion)

    assert resultado["creada"] is False
    assert "fallo simulado" in resultado["error"]

    monkeypatch.undo()
    assert sesion.get(HorarioDisponible, 1).disponible is True
    assert sesion.query(Reservacion).count() == 0
