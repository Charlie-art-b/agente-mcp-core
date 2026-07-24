"""
Datos de ejemplo (seed)
=========================
Carga datos de prueba: un par de clientes, servicios y horarios
disponibles. Es contenido de ejemplo genérico, no un módulo de negocio
real -- solo para poder probar el proyecto de punta a punta.

Uso:
    python -m app.db.seed
"""

from datetime import date, timedelta

from app.db.models import Cliente, HorarioDisponible, Servicio
from app.db.session import crear_tablas, obtener_engine_defecto, obtener_sesion


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

        manana = date.today() + timedelta(days=1)
        horarios = [
            HorarioDisponible(
                servicio_id=servicios[0].id,
                fecha=manana,
                hora_inicio="09:00",
                hora_fin="09:30",
                disponible=True,
            ),
            HorarioDisponible(
                servicio_id=servicios[0].id,
                fecha=manana,
                hora_inicio="10:00",
                hora_fin="10:30",
                disponible=True,
            ),
            HorarioDisponible(
                servicio_id=servicios[1].id,
                fecha=manana,
                hora_inicio="11:00",
                hora_fin="11:45",
                disponible=True,
            ),
        ]
        sesion.add_all(horarios)
        sesion.commit()

        # Sin caracteres no-ASCII: la consola de Windows (cp1252) revienta
        # con UnicodeEncodeError al imprimir símbolos como ✓.
        print(f"[OK] {len(clientes)} clientes creados")
        print(f"[OK] {len(servicios)} servicios creados")
        print(f"[OK] {len(horarios)} horarios disponibles creados")

    finally:
        sesion.close()


if __name__ == "__main__":
    print("Sembrando datos de ejemplo...")
    sembrar_datos_ejemplo()
    print("Listo.")