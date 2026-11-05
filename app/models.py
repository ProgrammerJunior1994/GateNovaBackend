from datetime import datetime, timezone
from sqlalchemy import (
    BigInteger, DateTime, ForeignKey, String, Text, CheckConstraint
)
from sqlalchemy.dialects.postgresql import ENUM
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

class User(Base):
    __tablename__ = "users"
    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    institutional_code: Mapped[int] = mapped_column("institutional_id", BigInteger, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    last_name: Mapped[str] = mapped_column(String(80), nullable=False)
    role: Mapped[str] = mapped_column(
    "rol",
    ENUM(
        "personal administrativo",
        "docente",
        "alumno",
        "servicios generales",
        name="rol_user",
        create_type=False
    ),
    nullable=False
)

    cards: Mapped[list["Card"]] = relationship(back_populates="user")
    vehicles: Mapped[list["Vehicle"]] = relationship(back_populates="user")

# SOLUCIONAR PROBLEMAS CON LOS TIPOS DE DATOA "rol_user"

class Card(Base):
    __tablename__ = "cards"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'disabled', 'lost')", name="ck_cards_status"),
    )

    card_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    card_code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)

    user: Mapped["User"] = relationship(back_populates="cards")


class Vehicle(Base):
    __tablename__ = "vehicles"
    __table_args__ = (
        CheckConstraint("status IN ('active', 'inactive')", name="ck_vehicles_status"),
    )

    vehicle_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    trademark: Mapped[str] = mapped_column(String(40), nullable=False)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    plate: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.user_id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)

    user: Mapped["User"] = relationship(back_populates="vehicles")


class AccessPoint(Base):
    __tablename__ = "access_points"
    __table_args__ = (
        CheckConstraint("direction IN ('entry', 'exit')", name="ck_access_points_direction"),
        CheckConstraint("status IN ('active', 'inactive')", name="ck_access_points_status"),
    )

    access_point_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    location: Mapped[str] = mapped_column(String(120), nullable=False)
    direction: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)


class AccessLog(Base):
    __tablename__ = "access_logs"
    __table_args__ = (
        CheckConstraint("access_type IN ('entry', 'exit')", name="ck_access_logs_type"),
        CheckConstraint("access_result IN ('authorized', 'denied')", name="ck_access_logs_result"),
    )

    access_log_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, index=True)
    access_datetime: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    access_type: Mapped[str] = mapped_column(String(10), nullable=False)
    access_result: Mapped[str] = mapped_column(String(15), nullable=False)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("cards.card_id"), nullable=True)
    vehicle_id: Mapped[int | None] = mapped_column(ForeignKey("vehicles.vehicle_id"), nullable=True)
    access_point_id: Mapped[int] = mapped_column(ForeignKey("access_points.access_point_id"), nullable=False)
    card_code_read: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    card: Mapped["Card | None"] = relationship()
    vehicle: Mapped["Vehicle | None"] = relationship()
    access_point: Mapped["AccessPoint"] = relationship()
