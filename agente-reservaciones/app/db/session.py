"""
Conexión a la base de datos
=============================
Crea el engine y las sesiones de SQLAlchemy a partir de DATABASE_URL
(ver .env). En producción esto apunta a Postgres (vía Docker); en tests
se puede apuntar a SQLite en memoria sin cambiar nada del resto del
código -- por eso `crear_engine` recibe la URL como parámetro.
"""

import os

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.db.models import Base

DATABASE_URL_DEFECTO = os.environ.get(
    "DATABASE_URL",
    "postgresql://agente:agente_dev_password@localhost:5432/agente_reservaciones",
)


def crear_engine(database_url: str = DATABASE_URL_DEFECTO):
    """
    Crea un engine de SQLAlchemy. `connect_args` con
    `check_same_thread=False` solo aplica (y solo hace falta) cuando la
    URL es SQLite; Postgres lo ignora sin problema si se pasara igual,
    pero lo condicionamos para que quede explícito.
    """
    connect_args = {}
    if database_url.startswith("sqlite"):
        connect_args = {"check_same_thread": False}

    return create_engine(database_url, connect_args=connect_args)


def crear_tablas(engine) -> None:
    """Crea todas las tablas definidas en app/db/models.py si no existen."""
    Base.metadata.create_all(engine)


def crear_fabrica_sesiones(engine) -> sessionmaker:
    return sessionmaker(bind=engine, expire_on_commit=False)


# --- Uso por defecto (producción / desarrollo normal) ---
# Se crean de forma perezosa (no al importar el módulo) para que los
# tests puedan importar este archivo sin necesitar el driver de Postgres
# instalado ni una base de datos real disponible.
_engine = None
_FabricaSesiones = None


def obtener_engine_defecto():
    global _engine
    if _engine is None:
        _engine = crear_engine()
    return _engine


def obtener_sesion() -> Session:
    """Devuelve una nueva sesión lista para usar (recordá cerrarla)."""
    global _FabricaSesiones
    if _FabricaSesiones is None:
        _FabricaSesiones = crear_fabrica_sesiones(obtener_engine_defecto())
    return _FabricaSesiones()