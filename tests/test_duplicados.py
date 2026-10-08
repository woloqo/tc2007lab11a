"""Tarjeta 2 · Envié una vez, aparecieron dos.

El contrato: el teléfono manda `Idempotency-Key` con un UUID que inventa al abrir
la pantalla de publicar. El mismo envío con la misma clave devuelve el aviso que ya
se guardó; la misma clave con otro contenido es un error. Sin clave, cada envío es
un aviso nuevo: publicar dos avisos con el mismo título es válido.
"""

import uuid

from fastapi.testclient import TestClient

from .conftest import Persona

CUERPO = {"titulo": "Feria de proyectos", "cuerpo": "El viernes a las 12:00 en el patio central."}


def avisos_de(cliente: TestClient, quien: Persona) -> list[dict]:
    return [a for a in cliente.get("/api/avisos", headers=quien.headers).json() if a["autor"] == quien.usuario]


def test_sin_clave_dos_envios_son_dos_avisos(ana: Persona, publicar):
    primero = publicar(ana, titulo="Feria de proyectos")
    segundo = publicar(ana, titulo="Feria de proyectos")

    assert primero["id"] != segundo["id"]


def test_reintentar_con_la_misma_clave_no_crea_otro_aviso(cliente: TestClient, ana: Persona):
    headers = {**ana.headers, "Idempotency-Key": str(uuid.uuid4())}

    primero = cliente.post("/api/avisos", headers=headers, json=CUERPO)
    reintento = cliente.post("/api/avisos", headers=headers, json=CUERPO)

    assert primero.status_code == 201
    assert reintento.status_code == 201
    assert reintento.json()["id"] == primero.json()["id"]
    assert len(avisos_de(cliente, ana)) == 1


def test_la_misma_clave_con_otro_contenido_se_rechaza(cliente: TestClient, ana: Persona):
    headers = {**ana.headers, "Idempotency-Key": str(uuid.uuid4())}
    cliente.post("/api/avisos", headers=headers, json=CUERPO)

    r = cliente.post("/api/avisos", headers=headers, json={**CUERPO, "titulo": "Otro aviso distinto"})

    assert r.status_code == 422
    assert r.json()["code"] == "clave_reutilizada"
    assert len(avisos_de(cliente, ana)) == 1


def test_la_clave_de_ana_no_le_estorba_a_bruno(cliente: TestClient, ana: Persona, bruno: Persona):
    # La clave es única por persona, no en todo el servidor: Bruno no puede «adivinar»
    # la clave de Ana y recibir su aviso, ni bloquearle una publicación.
    clave = str(uuid.uuid4())

    de_ana = cliente.post("/api/avisos", headers={**ana.headers, "Idempotency-Key": clave}, json=CUERPO)
    de_bruno = cliente.post("/api/avisos", headers={**bruno.headers, "Idempotency-Key": clave}, json=CUERPO)

    assert de_bruno.status_code == 201
    assert de_bruno.json()["id"] != de_ana.json()["id"]
    assert de_bruno.json()["autor"] == bruno.usuario