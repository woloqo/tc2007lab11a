from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


class Usuario(Base):
    """Quién es quién. La contraseña NO está: está su hash Argon2 (que ya trae su sal adentro)."""

    __tablename__ = "usuarios"

    usuario: Mapped[str] = mapped_column(String(32), primary_key=True)
    password_hash: Mapped[str] = mapped_column(Text)
    rol: Mapped[str] = mapped_column(String(16))  # "alumno" | "profesor"
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Sesion(Base):
    """Una fila por login. Guarda el HASH del refresh token, nunca el token."""

    __tablename__ = "sesiones"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario: Mapped[str] = mapped_column(ForeignKey("usuarios.usuario"), index=True)
    refresh_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[int] = mapped_column(BigInteger)  # epoch en segundos
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class Aviso(Base):
    """El tablón. Cualquiera con sesión lo lee; solo un profesor escribe."""

    __tablename__ = "avisos"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    titulo: Mapped[str] = mapped_column(String(60))
    cuerpo: Mapped[str] = mapped_column(String(400))
    autor: Mapped[str] = mapped_column(String(32))
    # La CLAVE del objeto en el almacén ("3f2a….jpg"), no la imagen. NULL si el aviso no lleva.
    imagen: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

class Idempotencia(Base):
    """Una fila por publicación que llegó con `Idempotency-Key`: quién, con qué clave, qué aviso salió.

    La restricción única es la que de verdad impide el duplicado. La consulta de
    `crear` ataja el reintento normal; si dos envíos llegan al mismo tiempo, los dos
    pasan la consulta, y PostgreSQL deja guardar solo a uno.
    """

    __tablename__ = "idempotencia"
    __table_args__ = (UniqueConstraint("usuario", "clave"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    usuario: Mapped[str] = mapped_column(String(32))
    clave: Mapped[str] = mapped_column(String(64))
    # sha256 del aviso que llegó con esa clave: la misma clave con otro contenido no es un reintento.
    huella: Mapped[str] = mapped_column(String(64))
    # Si se borra el aviso, su fila se va con él (ON DELETE CASCADE, lo hace PostgreSQL).
    aviso_id: Mapped[int] = mapped_column(ForeignKey("avisos.id", ondelete="CASCADE"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())