"""Tarjeta 1 · Tengo sesión, pero no permiso.

La regla: un profesor borra SUS avisos. Un alumno no borra ninguno.

Una de estas pruebas falla. No es un error de la prueba: es el defecto. Su trabajo
es corregir el servidor hasta que pase, sin que dejen de pasar las otras dos.
"""

from fastapi.testclient import TestClient

from .conftest import Persona


def test_ana_puede_borrar_su_propio_aviso(cliente: TestClient, ana: Persona, publicar):
    aviso = publicar(ana)

    r = cliente.delete(f"/api/avisos/{aviso['id']}", headers=ana.headers)

    assert r.status_code == 204


def test_una_alumna_no_puede_borrar_avisos(cliente: TestClient, ana: Persona, carla: Persona, publicar):
    aviso = publicar(ana)

    r = cliente.delete(f"/api/avisos/{aviso['id']}", headers=carla.headers)

    assert r.status_code == 403


def test_bruno_no_puede_borrar_el_aviso_de_ana(cliente: TestClient, ana: Persona, bruno: Persona, publicar):
    aviso = publicar(ana)

    r = cliente.delete(f"/api/avisos/{aviso['id']}", headers=bruno.headers)

    assert r.status_code == 403, f"Bruno pudo borrar el aviso de Ana: el servidor respondió {r.status_code}"
    # Y el aviso sigue en el tablón.
    tablon = cliente.get("/api/avisos", headers=ana.headers).json()
    assert aviso["id"] in [a["id"] for a in tablon]