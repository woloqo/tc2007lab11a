"""El almacén de objetos, en un solo archivo. Todo lo demás le habla a estas seis
funciones y no sabe que del otro lado hay S3.

Se usa boto3, el cliente oficial de Amazon S3: habla con cualquier almacén
compatible —RustFS aquí, MinIO, Cloudflare R2, Amazon S3 en producción—
cambiando solo `S3_ENDPOINT` y las llaves.

Un objeto es una clave ("3f2a….jpg"), unos bytes y su tipo. No hay carpetas, no
hay consultas, no hay transacciones: guardar, leer, preguntar si existe, listar y borrar.
Por eso las imágenes van aquí y no en PostgreSQL, y por eso la base solo guarda
la clave.
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Any

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from .config import settings

_s3 = boto3.client(
    "s3",
    endpoint_url=settings.s3_endpoint,
    aws_access_key_id=settings.s3_access_key,
    aws_secret_access_key=settings.s3_secret_key,
    # S3 exige una región aunque el almacén sea tuyo; RustFS acepta esta.
    region_name="us-east-1",
    # "path": http://almacen:9000/avisos/clave. El estilo por omisión pone el bucket en el
    # nombre del host (avisos.almacen), y ese nombre no existe en la red de Docker.
    config=Config(s3={"addressing_style": "path"}, connect_timeout=3, retries={"max_attempts": 2}),
)


def preparar() -> None:
    """Crea el bucket si no existe. Se llama una vez, al arrancar."""
    try:
        _s3.head_bucket(Bucket=settings.s3_bucket)
    except ClientError:
        _s3.create_bucket(Bucket=settings.s3_bucket)


def guardar(clave: str, datos: bytes, tipo: str) -> None:
    _s3.put_object(Bucket=settings.s3_bucket, Key=clave, Body=datos, ContentType=tipo)


def abrir(clave: str) -> dict[str, Any] | None:
    """El objeto listo para mandarse por partes, o None si no existe.

    `Body` es un flujo: los bytes salen del almacén conforme el cliente los lee,
    sin cargar la imagen completa en la memoria del servidor.
    """
    try:
        return _s3.get_object(Bucket=settings.s3_bucket, Key=clave)
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return None
        raise


def existe(clave: str) -> bool:
    try:
        _s3.head_object(Bucket=settings.s3_bucket, Key=clave)
        return True
    except ClientError as e:
        if e.response["Error"]["Code"] in ("NoSuchKey", "404"):
            return False
        raise


def borrar(clave: str) -> None:
    # Borrar lo que no existe no es error en S3: así borrar dos veces no truena.
    _s3.delete_object(Bucket=settings.s3_bucket, Key=clave)


def listar() -> Iterator[tuple[str, datetime]]:
    """Cada objeto del bucket: su clave y cuándo se guardó. S3 los entrega de mil en mil."""
    for pagina in _s3.get_paginator("list_objects_v2").paginate(Bucket=settings.s3_bucket):
        for objeto in pagina.get("Contents", []):
            yield objeto["Key"], objeto["LastModified"]