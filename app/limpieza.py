"""La limpieza de imágenes huérfanas: las que están en el almacén y ningún aviso usa.

Publicar con imagen son dos peticiones, y no hay una transacción que abarque a
PostgreSQL y a RustFS: si el aviso falla, la imagen ya subió. Eso no se puede
impedir; se limpia después. Se corre a mano, o cada noche desde un cron:

    docker compose exec api uv run --no-sync python -m app.limpieza
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from . import almacen
from .db import SessionLocal
from .models import Aviso

# El margen protege a quien está publicando en este momento: su imagen ya subió y
# su aviso todavía no llega. Solo se borra lo que lleva más de una hora sin aviso.
MARGEN = timedelta(hours=1)


def limpiar_huerfanas(margen: timedelta = MARGEN, ahora: datetime | None = None) -> list[str]:
    """Borra las imágenes que ningún aviso usa y que son más viejas que `margen`. Devuelve sus claves.

    `ahora` es un parámetro para que una prueba decida qué hora es, como
    `tiempoRelativo` en la app de la Práctica 11.
    """
    ahora = ahora or datetime.now(timezone.utc)
    with SessionLocal() as db:
        usadas = set(db.scalars(select(Aviso.imagen).where(Aviso.imagen.is_not(None))))
    borradas = []
    for clave, guardada in almacen.listar():
        if clave not in usadas and ahora - guardada > margen:
            almacen.borrar(clave)
            borradas.append(clave)
    return borradas


if __name__ == "__main__":
    borradas = limpiar_huerfanas()
    print(f"{len(borradas)} imágenes huérfanas borradas")