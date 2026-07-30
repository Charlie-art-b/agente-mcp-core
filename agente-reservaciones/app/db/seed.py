"""
Datos de ejemplo (seed)
=========================
Carga datos de prueba: un par de clientes, servicios, y una buena cantidad
de horarios disponibles a lo largo de las próximas semanas. Es contenido de
ejemplo genérico, no un módulo de negocio real -- solo para poder probar el
proyecto de punta a punta con espacio de sobra para agendar.

Uso:
    python -m app.db.seed
"""

from datetime import date, datetime, timedelta

from app.db.models import Cliente, HorarioDisponible, Servicio
from app.db.session import crear_tablas, obtener_engine_defecto, obtener_sesion

# Cuántos días hacia adelante generar horarios (desde mañana).
DIAS_A_FUTURO = 14

SERVICIOS_DEMO = [
    {"nombre": "Corte de cabello", "duracion_minutos": 30, "precio": 5000},
    {"nombre": "Corte + barba", "duracion_minutos": 45, "precio": 7000},
    {"nombre": "Cejas", "duracion_minutos": 15, "precio": 1500},
    {"nombre": "Todo incluido", "duracion_minutos": 60, "precio": 10000},
]

# Horas de inicio de los turnos, por servicio. Se combinan con cada día para
# generar los horarios disponibles.
HORAS_POR_SERVICIO = {
    "Corte de cabello": ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"],
    "Corte + barba": ["09:30", "10:30", "13:30", "15:30"],
    "Cejas": ["10:15", "13:15", "16:15"],
    "Todo incluido": ["09:00", "12:00", "15:00"],
}


def _sumar_minutos(hora_hhmm: str, minutos: int) -> str:
    """'09:00' + 30 -> '09:30'. Calcula la hora de fin desde la de inicio."""
    t = datetime.strptime(hora_hhmm, "%H:%M") + timedelta(minutes=minutos)
    return t.strftime("%H:%M")


def _obtener_o_crear_servicio(sesion, datos: dict) -> Servicio:
    servicio = sesion.query(Servicio).filter(Servicio.nombre == datos["nombre"]).first()
    if servicio is None:
        servicio = Servicio(**datos)
        sesion.add(servicio)
        sesion.flush()
    else:
        servicio.duracion_minutos = datos["duracion_minutos"]
        servicio.precio = datos["precio"]
    return servicio


def sembrar_datos_ejemplo() -> None:
    crear_tablas(obtener_engine_defecto())
    sesion = obtener_sesion()

    try:
        clientes = []
        if sesion.query(Cliente).count() == 0:
            clientes = [
                Cliente(nombre="Carlos Mora", telefono="8888-0001", email="carlos@example.com"),
                Cliente(nombre="Marco Solís", telefono="8888-0002", email="marco@example.com"),
            ]
            sesion.add_all(clientes)

        servicios = []
        for datos in SERVICIOS_DEMO:
            servicios.append(_obtener_o_crear_servicio(sesion, datos))

        sesion.flush()

        hoy = date.today()
        horarios = []
        for dia_delta in range(1, DIAS_A_FUTURO + 1):
            dia = hoy + timedelta(days=dia_delta)
            for servicio in servicios:
                for hora_inicio in HORAS_POR_SERVICIO.get(servicio.nombre, []):
                    existente = (
                        sesion.query(HorarioDisponible)
                        .filter(
                            HorarioDisponible.servicio_id == servicio.id,
                            HorarioDisponible.fecha == dia,
                            HorarioDisponible.hora_inicio == hora_inicio,
                        )
                        .first()
                    )
                    if existente is None:
                        horarios.append(
                            HorarioDisponible(
                                servicio_id=servicio.id,
                                fecha=dia,
                                hora_inicio=hora_inicio,
                                hora_fin=_sumar_minutos(hora_inicio, servicio.duracion_minutos),
                                disponible=True,
                            )
                        )

        if horarios:
            sesion.add_all(horarios)

        sesion.commit()

        print(f"[OK] {len(clientes)} clientes creados")
        print(f"[OK] {len(servicios)} servicios definidos")
        print(f"[OK] {len(horarios)} horarios disponibles creados")

    finally:
        sesion.close()


if __name__ == "__main__":
    print("Sembrando datos de ejemplo para la barbería...")
    sembrar_datos_ejemplo()
    print("Listo.")
