"""Tarjeta 3 · La imagen que nadie usa.

Publicar con imagen son dos peticiones: primero la imagen, después el aviso. Si la
segunda falla, la primera ya pasó, y eso no cambia. Lo que cambia es que ahora
alguien limpia: `app/limpieza.py`.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app import almacen
from app.limpieza import limpiar_huerfanas

from .conftest import Persona


def test_si_el_aviso_falla_la_imagen_se_queda_en_el_almacen(cliente: TestClient, ana: Persona, subir):
    clave = subir(ana)

    # El aviso no pasa la validación del servidor (título de una letra).
    r = cliente.post("/api/avisos", headers=ana.headers, json={"titulo": "X", "cuerpo": "Un cuerpo válido para el aviso.", "imagen": clave})
    assert r.status_code == 422

    try:
        assert almacen.existe(clave), "La imagen ya no está en el almacén"
    finally:
        almacen.borrar(clave)  # la prueba limpia lo que dejó


def test_la_limpieza_borra_la_huerfana_y_respeta_la_que_usa_un_aviso(ana: Persona, subir, publicar):
    usada = subir(ana)
    publicar(ana, imagen=usada)
    huerfana = subir(ana)

    # Dentro de dos horas: la huérfana ya pasó el margen de una hora.
    limpiar_huerfanas(ahora=datetime.now(timezone.utc) + timedelta(hours=2))

    assert almacen.existe(usada), "Se borró una imagen que un aviso sí usa"
    assert not almacen.existe(huerfana), "La huérfana sigue en el almacén"


def test_la_limpieza_no_toca_una_imagen_recien_subida(ana: Persona, subir):
    # Quien está publicando ahora mismo: su imagen ya subió y su aviso todavía no llega.
    clave = subir(ana)

    try:
        limpiar_huerfanas()
        assert almacen.existe(clave), "Se borró la imagen de alguien que estaba publicando"
    finally:
        almacen.borrar(clave)