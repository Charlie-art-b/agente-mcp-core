"""
Modelos de datos
=================
Representación en Python de las tablas del negocio. Esta es la ÚNICA
fuente de verdad del esquema (reemplaza a init.sql como referencia
"viva" -- init.sql queda solo como documentación de arranque rápido
para Postgres, pero las tablas reales las crea SQLAlchemy a partir de
estos modelos, tanto en Postgres como en SQLite para tests).

Dominio: reservaciones de un negocio pequeño (salón, restaurante,
consultorio, etc. -- placeholder, no es un módulo de negocio final).
"""

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Cliente(Base):
    __tablename__ = "clientes"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    telefono: Mapped[str | None] = mapped_column(String(30), unique=True)
    email: Mapped[str | None] = mapped_column(String(150))
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    reservaciones: Mapped[list["Reservacion"]] = relationship(back_populates="cliente")
    tickets: Mapped[list["TicketEscalado"]] = relationship(back_populates="cliente")


class Servicio(Base):
    __tablename__ = "servicios"

    id: Mapped[int] = mapped_column(primary_key=True)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    duracion_minutos: Mapped[int] = mapped_column(nullable=False)
    precio: Mapped[float] = mapped_column(Numeric(10, 2), nullable=False)

    horarios: Mapped[list["HorarioDisponible"]] = relationship(back_populates="servicio")


class HorarioDisponible(Base):
    __tablename__ = "horarios_disponibles"

    id: Mapped[int] = mapped_column(primary_key=True)
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicios.id"))
    fecha: Mapped[datetime] = mapped_column(Date, nullable=False)
    hora_inicio: Mapped[str] = mapped_column(String(5), nullable=False)  # "09:00"
    hora_fin: Mapped[str] = mapped_column(String(5), nullable=False)  # "10:00"
    disponible: Mapped[bool] = mapped_column(Boolean, default=True)

    servicio: Mapped["Servicio"] = relationship(back_populates="horarios")
    reservacion: Mapped["Reservacion | None"] = relationship(back_populates="horario")


class Reservacion(Base):
    __tablename__ = "reservaciones"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    servicio_id: Mapped[int] = mapped_column(ForeignKey("servicios.id"))
    horario_id: Mapped[int] = mapped_column(ForeignKey("horarios_disponibles.id"))
    estado: Mapped[str] = mapped_column(String(30), default="confirmada")
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    cliente: Mapped["Cliente"] = relationship(back_populates="reservaciones")
    servicio: Mapped["Servicio"] = relationship()
    horario: Mapped["HorarioDisponible"] = relationship(back_populates="reservacion")


class TicketEscalado(Base):
    __tablename__ = "tickets_escalados"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int] = mapped_column(ForeignKey("clientes.id"))
    motivo: Mapped[str] = mapped_column(Text, nullable=False)
    estado: Mapped[str] = mapped_column(String(30), default="abierto")
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )

    cliente: Mapped["Cliente"] = relationship(back_populates="tickets")


class InteraccionLog(Base):
    """
    Registro de cada interacción del agente. Se usa desde la Fase 6
    (logging/observabilidad), pero se define desde ya junto al resto
    del esquema para no tener que hacer una migración después.
    """

    __tablename__ = "interacciones_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    cliente_id: Mapped[int | None] = mapped_column(ForeignKey("clientes.id"))
    mensaje_usuario: Mapped[str] = mapped_column(Text, nullable=False)
    tool_llamada: Mapped[str | None] = mapped_column(String(100))
    tool_input: Mapped[dict | None] = mapped_column(JSON)
    tool_output: Mapped[dict | None] = mapped_column(JSON)
    respuesta_agente: Mapped[str | None] = mapped_column(Text)
    tokens_input: Mapped[int | None]
    tokens_output: Mapped[int | None]
    costo_usd: Mapped[float | None] = mapped_column(Numeric(10, 6))
    latencia_ms: Mapped[int | None]
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc)
    )