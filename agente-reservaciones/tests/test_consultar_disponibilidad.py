"""
Tests de la tool consultar_disponibilidad
==========================================
Prueban la tool de forma aislada, sin el LLM ni el servidor MCP de por
medio, contra SQLite en memoria -- no hace falta Postgres corriendo.

La sesión se inyecta en la tool (parámetro `sesion`), que es justamente
para lo que existe ese parámetro.
"""

from datetime import date

import pytest

from app.db.models import Cliente, HorarioDisponible, Reservacion, Servicio
from app.db.session import crear_engine, crear_fabrica_sesiones, crear_tablas
from app.tools.consultar_disponibilidad import consultar_disponibilidad

FECHA = date(2026, 8, 1)
FECHA_STR = "2026-08-01"


@pytest.fixture
def sesion():
    """Base SQLite en memoria con datos de prueba ya cargados."""
    engine = crear_engine("sqlite:///:memory:")
    crear_tablas(engine)
    s = crear_fabrica_sesiones(engine)()

    corte = Servicio(nombre="Corte de cabello", duracion_minutos=30, precio=8000)
    manicure = Servicio(nombre="Manicure", duracion_minutos=45, precio=12000)
    s.add_all([corte, manicure])
    s.flush()

    s.add_all(
        [
            # Se agregan desordenados a propósito, para probar el orden.
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
                hora_inicio="09:00",
                hora_fin="09:30",
                disponible=True,
            ),
            # Ya reservado: no debe aparecer.
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=FECHA,
                hora_inicio="11:00",
                hora_fin="11:30",
                disponible=False,
            ),
            HorarioDisponible(
                servicio_id=manicure.id,
                fecha=FECHA,
                hora_inicio="14:00",
                hora_fin="14:45",
                disponible=True,
            ),
            # Otro día: no debe aparecer al consultar FECHA.
            HorarioDisponible(
                servicio_id=corte.id,
                fecha=date(2026, 8, 2),
                hora_inicio="09:00",
                hora_fin="09:30",
                disponible=True,
            ),
        ]
    )
    s.commit()

    yield s
    s.close()


def test_devuelve_los_horarios_libres_de_la_fecha(sesion):
    resultado = consultar_disponibilidad(FECHA_STR, sesion=sesion)

    # 2 de corte + 1 de manicure. El ocupado y el de otro día no cuentan.
    assert resultado["total"] == 3


def test_no_devuelve_horarios_ya_ocupados(sesion):
    resultado = consultar_disponibilidad(FECHA_STR, sesion=sesion)

    horas = [h["hora_inicio"] for h in resultado["disponibles"]]
    assert "11:00" not in horas


def test_no_devuelve_horarios_de_otra_fecha(sesion):
    resultado = consultar_disponibilidad("2026-08-02", sesion=sesion)

    assert resultado["total"] == 1
    assert resultado["disponibles"][0]["hora_inicio"] == "09:00"


def test_filtra_por_servicio_con_nombre_parcial(sesion):
    """El agente manda 'corte', no 'Corte de cabello'."""
    resultado = consultar_disponibilidad(FECHA_STR, servicio="corte", sesion=sesion)

    assert resultado["total"] == 2
    assert all(h["servicio"] == "Corte de cabello" for h in resultado["disponibles"])


def test_el_filtro_de_servicio_ignora_mayusculas(sesion):
    resultado = consultar_disponibilidad(FECHA_STR, servicio="MANICURE", sesion=sesion)

    assert resultado["total"] == 1
    assert resultado["disponibles"][0]["servicio"] == "Manicure"


def test_resultados_vienen_ordenados_por_hora(sesion):
    resultado = consultar_disponibilidad(FECHA_STR, servicio="corte", sesion=sesion)

    horas = [h["hora_inicio"] for h in resultado["disponibles"]]
    assert horas == sorted(horas)


def test_incluye_horario_id_para_poder_encadenar_con_crear_reservacion(sesion):
    """Sin el horario_id, el agente no puede reservar lo que acaba de ver."""
    resultado = consultar_disponibilidad(FECHA_STR, servicio="corte", sesion=sesion)

    primero = resultado["disponibles"][0]
    assert isinstance(primero["horario_id"], int)

    # El id devuelto tiene que existir de verdad en la base.
    assert sesion.get(HorarioDisponible, primero["horario_id"]) is not None


def test_incluye_precio_como_float_serializable(sesion):
    """precio es Numeric (Decimal) en la base y Decimal no va a JSON."""
    resultado = consultar_disponibilidad(FECHA_STR, servicio="corte", sesion=sesion)

    precio = resultado["disponibles"][0]["precio"]
    assert isinstance(precio, float)
    assert precio == 8000.0


def test_servicio_inexistente_avisa_y_sugiere_los_que_si_existen(sesion):
    resultado = consultar_disponibilidad(
        FECHA_STR, servicio="masaje tailandés", sesion=sesion
    )

    assert resultado["disponibles"] == []
    assert "error" in resultado
    assert "Corte de cabello" in resultado["servicios_disponibles"]
    assert "Manicure" in resultado["servicios_disponibles"]


def test_fecha_con_formato_invalido_devuelve_error_claro(sesion):
    resultado = consultar_disponibilidad("01/08/2026", sesion=sesion)

    assert resultado["disponibles"] == []
    assert "error" in resultado
    assert "YYYY-MM-DD" in resultado["error"]


def test_fecha_sin_horarios_devuelve_lista_vacia_sin_error(sesion):
    """No hay campo ese día, pero no es un error: es una respuesta válida."""
    resultado = consultar_disponibilidad("2026-12-25", sesion=sesion)

    assert resultado["disponibles"] == []
    assert resultado["total"] == 0
    assert "error" not in resultado


def test_horario_reservado_deja_de_aparecer(sesion):
    """Simula el efecto de crear_reservacion sobre esta tool."""
    antes = consultar_disponibilidad(FECHA_STR, servicio="corte", sesion=sesion)
    horario_id = antes["disponibles"][0]["horario_id"]

    cliente = Cliente(nombre="Ana", telefono="8888-0001")
    sesion.add(cliente)
    sesion.flush()

    horario = sesion.get(HorarioDisponible, horario_id)
    horario.disponible = False
    sesion.add(
        Reservacion(
            cliente_id=cliente.id,
            servicio_id=horario.servicio_id,
            horario_id=horario.id,
        )
    )
    sesion.commit()

    despues = consultar_disponibilidad(FECHA_STR, servicio="corte", sesion=sesion)

    assert despues["total"] == antes["total"] - 1
    assert horario_id not in [h["horario_id"] for h in despues["disponibles"]]
