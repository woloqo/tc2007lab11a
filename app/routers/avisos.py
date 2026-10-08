import json
import time
from collections.abc import Iterator

from fastapi import APIRouter, Depends, Header, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import almacen
from ..db import SessionLocal, get_db
from ..deps import Identidad, requiere_profesor, usuario_actual
from ..errors import ApiError
from ..models import Aviso, Idempotencia
from ..schemas import AvisoOut, NuevoAviso
from ..security import sha256

router = APIRouter(prefix="/avisos", tags=["avisos"])


@router.get("", response_model=list[AvisoOut])
def listar(desde: int = 0, _: Identidad = Depends(usuario_actual), db: Session = Depends(get_db)) -> list[Aviso]:
    """Todo el tablón exige sesión, incluso leerlo. `?desde=N`: solo los avisos con id mayor a N."""
    return list(db.scalars(select(Aviso).where(Aviso.id > desde).order_by(Aviso.id.desc()).limit(100)))


@router.get("/stream")
def stream(request: Request, quien: Identidad = Depends(usuario_actual), desde: int = 0) -> StreamingResponse:
    """Server-Sent Events: la conexión se queda abierta y empuja cada aviso nuevo.

    No hay pub/sub: el servidor consulta la tabla cada 3 s. Para el reto alcanza,
    y deja claro quién sondea a quién: el servidor a su base, nunca el teléfono
    al servidor. Vive hasta que el token expira; el cliente reconecta con
    `Last-Event-ID` y no pierde nada de en medio.
    """
    ultimo = int(request.headers.get("Last-Event-ID") or desde or 0)

    def eventos() -> Iterator[str]:
        nonlocal ultimo
        yield f": conectado como {quien.usuario}, desde el aviso {ultimo}\n\n"
        tic = 0
        while time.time() < quien.exp:
            # Una sesión corta por vuelta: la conexión vive minutos, una sesión abierta no debe.
            with SessionLocal() as db:
                nuevos = db.scalars(select(Aviso).where(Aviso.id > ultimo).order_by(Aviso.id.asc()).limit(50)).all()
            for aviso in nuevos:
                ultimo = aviso.id
                data = json.dumps(AvisoOut.model_validate(aviso).model_dump(), ensure_ascii=False)
                yield f"id: {aviso.id}\nevent: aviso\ndata: {data}\n\n"
            tic += 1
            if tic % 5 == 0:
                yield ": ping\n\n"
            time.sleep(3)
        # El token venció: se cierra a propósito. El cliente refresca y vuelve.
        yield "event: fin\ndata: token_expirado\n\n"

    return StreamingResponse(eventos(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@router.delete("/{id}", status_code=204)
def borrar(id: int, quien: Identidad = Depends(requiere_profesor), db: Session = Depends(get_db)) -> Response:
    aviso = db.get(Aviso, id)
    if aviso is None:
        raise ApiError(404, f"No existe el aviso {id}")
    # Tener el rol no basta: el aviso tiene que ser suyo. El autor lo guardó el servidor
    # al publicar, con la identidad del token; aquí se compara con la del token de ahora.
    if aviso.autor != quien.usuario:
        raise ApiError(403, "Solo quien publicó el aviso puede borrarlo", "no_es_tuyo", f'El aviso {id} es de "{aviso.autor}".')
    db.delete(aviso)
    db.commit()
    # Primero la fila y después el objeto: si el almacén falla, queda un archivo huérfano
    # (estorba) en vez de un aviso que apunta a una imagen que ya no existe (truena).
    if aviso.imagen:
        almacen.borrar(aviso.imagen)
    return Response(status_code=204)

def ya_publicado(db: Session, quien: Identidad, clave: str, huella: str) -> Aviso | None:
    """El aviso que ya salió con esta clave, o None si es la primera vez que llega."""
    previo = db.scalar(select(Idempotencia).where(Idempotencia.usuario == quien.usuario, Idempotencia.clave == clave))
    if previo is None:
        return None
    if previo.huella != huella:
        raise ApiError(
            422,
            "Esa clave ya se usó para publicar otro aviso",
            "clave_reutilizada",
            "Genera una Idempotency-Key nueva por publicación; repítela solo al reintentar la misma.",
        )
    return db.get(Aviso, previo.aviso_id)

@router.post("", response_model=AvisoOut, status_code=201)
def crear(
    body: NuevoAviso,
    quien: Identidad = Depends(requiere_profesor),
    db: Session = Depends(get_db),
    # La inventa el teléfono: una por publicación, la misma en cada reintento. Es opcional:
    # sin ella, cada envío es un aviso nuevo, como antes.
    clave: str | None = Header(default=None, alias="Idempotency-Key", max_length=64),
) -> Aviso:
    huella = sha256(body.model_dump_json())
    if clave is not None and (previo := ya_publicado(db, quien, clave, huella)) is not None:
        return previo
    # Una clave con buena forma no basta: la imagen tiene que estar en el almacén.
    if body.imagen is not None and not almacen.existe(body.imagen):
        raise ApiError(422, "Esa imagen no existe", "imagen_inexistente", "Súbela primero con POST /api/imagenes y manda la clave que te devuelve.")
    aviso = Aviso(titulo=body.titulo, cuerpo=body.cuerpo, autor=quien.usuario, imagen=body.imagen)
    db.add(aviso)
    if clave is not None:
        db.flush()  # PostgreSQL asigna aviso.id sin cerrar la transacción
        db.add(Idempotencia(usuario=quien.usuario, clave=clave, huella=huella, aviso_id=aviso.id))
    try:
        db.commit()  # el aviso y su clave se guardan juntos, o ninguno
    except IntegrityError:
        # Otro envío con la misma clave se guardó primero: los dos pasaron la consulta
        # de arriba, y la restricción única dejó pasar solo a uno. Se responde el suyo.
        db.rollback()
        previo = ya_publicado(db, quien, clave, huella) if clave else None
        if previo is None:
            raise
        return previo
    db.refresh(aviso)
    return aviso