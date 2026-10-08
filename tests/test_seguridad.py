"""Pruebas negativas: lo que el servidor tiene que RECHAZAR.

Ya pasan desde el primer día. Son la evidencia de seguridad del reto: «demuestren
al menos algunos casos en los que el sistema rechaza una acción no permitida».
"""

import uuid

from fastapi.testclient import TestClient

from app.config import settings
from app.db import SessionLocal
from app.models import Usuario
from app.security import sign_jwt

from .conftest import PNG_CHICO, Persona


def test_un_token_vencido_no_sirve(cliente: TestClient, carla: Persona):
    # Sin esperar cinco minutos: se firma con la llave real del servidor un token que venció
    # hace uno. Firmarlo con OTRA llave probaría la firma, no el vencimiento.
    vencido = sign_jwt(carla.usuario, carla.rol, -60, settings.jwt_secret)

    r = cliente.get("/api/avisos", headers={"Authorization": f"Bearer {vencido}"})

    assert r.status_code == 401
    assert r.json()["code"] == "token_expirado"


def test_mandar_rol_profesor_sin_el_codigo_crea_un_alumno(cliente: TestClient):
    # El cliente puede mandar lo que quiera. El rol lo decide el servidor, con el código.
    cuerpo = {"usuario": f"tramposa.{uuid.uuid4().hex[:8]}", "password": "secreta123", "rol": "profesor"}

    r = cliente.post("/api/auth/register", json=cuerpo)

    assert r.status_code == 201
    assert r.json()["rol"] == "alumno"


def test_una_alumna_no_puede_subir_imagenes(cliente: TestClient, carla: Persona):
    r = cliente.post("/api/imagenes", headers=carla.headers, files={"archivo": ("foto.png", PNG_CHICO, "image/png")})

    assert r.status_code == 403


def test_la_contrasena_no_se_guarda_en_claro(carla: Persona):
    # Se lee la fila directo de PostgreSQL, como la vería quien se robe un respaldo.
    with SessionLocal() as db:
        fila = db.get(Usuario, carla.usuario)

    assert fila is not None
    assert "secreta123" not in fila.password_hash
    assert fila.password_hash.startswith("$argon2id$")