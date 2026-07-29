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

# Horas de inicio de los turnos, por servicio. Se combinan con cada día para
# generar los horarios disponibles.
HORAS_POR_SERVICIO = {
    "Corte de cabello": ["09:00", "10:00", "11:00", "14:00", "15:00", "16:00"],
    "Manicure": ["09:00", "10:30", "14:00", "15:30"],
}


def _sumar_minutos(hora_hhmm: str, minutos: int) -> str:
    """'09:00' + 30 -> '09:30'. Calcula la hora de fin desde la de inicio."""
    t = datetime.strptime(hora_hhmm, "%H:%M") + timedelta(minutes=minutos)
    return t.strftime("%H:%M")


def sembrar_datos_ejemplo() -> None:
    crear_tablas(obtener_engine_defecto())
    sesion = obtener_sesion()

    try:
        if sesion.query(Cliente).count() > 0:
            print("Ya hay datos cargados, no se vuelve a sembrar.")
            return

        clientes = [
            Cliente(nombre="Ana Pérez", telefono="8888-0001", email="ana@example.com"),
            Cliente(nombre="Luis Gómez", telefono="8888-0002", email="luis@example.com"),
        ]
        servicios = [
            Servicio(nombre="Corte de cabello", duracion_minutos=30, precio=8000),
            Servicio(nombre="Manicure", duracion_minutos=45, precio=12000),
        ]

        sesion.add_all(clientes + servicios)
        sesion.flush()  # para que servicios ya tengan id antes de crear horarios

        # Un horario por cada (día futuro × servicio × hora de inicio). Genera
        # espacio de sobra para agendar sin quedarse sin cupos.
        #
        # La demo genera horarios TODOS los días (incluido domingo) para que
        # siempre haya disponibilidad "mañana". Un negocio real filtraría por
        # sus horarios de atención reales (ver data/documents/ejemplo_prueba.md).
        hoy = date.today()
        horarios = []
        for dia_delta in range(1, DIAS_A_FUTURO + 1):
            dia = hoy + timedelta(days=dia_delta)
            for servicio in servicios:
                for hora_inicio in HORAS_POR_SERVICIO[servicio.nombre]:
                    horarios.append(
                        HorarioDisponible(
                            servicio_id=servicio.id,
                            fecha=dia,
                            hora_inicio=hora_inicio,
                            hora_fin=_sumar_minutos(hora_inicio, servicio.duracion_minutos),
                            disponible=True,
                        )
                    )

        sesion.add_all(horarios)
        sesion.commit()

        # Sin caracteres no-ASCII: la consola de Windows (cp1252) revienta
        # con UnicodeEncodeError al imprimir símbolos como el de check.
        print(f"[OK] {len(clientes)} clientes creados")
        print(f"[OK] {len(servicios)} servicios creados")
        print(
            f"[OK] {len(horarios)} horarios disponibles creados "
            f"({DIAS_A_FUTURO} días x {len(servicios)} servicios)"
        )

    finally:
        sesion.close()


if __name__ == "__main__":
    print("Sembrando datos de ejemplo...")
    sembrar_datos_ejemplo()
    print("Listo.")
