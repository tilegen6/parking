"""Хранилище фотографий в MinIO (S3-совместимое)."""

import io
import json
import logging

from minio import Minio
from minio.error import S3Error

from src.config import settings

logger = logging.getLogger(__name__)


def _public_read_policy(bucket: str) -> str:
    """Политика анонимного чтения объектов — чтобы фото открывались на фронте."""
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )


class PhotoStorage:
    """Обёртка над MinIO для загрузки фото автомобилей и номеров."""

    def __init__(self) -> None:
        self._client: Minio | None = None
        self._bucket_ready = False

    @property
    def client(self) -> Minio:
        if self._client is None:
            self._client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_root_user,
                secret_key=settings.minio_root_password,
                secure=settings.minio_secure,
            )
        return self._client

    def ensure_bucket(self) -> None:
        """Создать bucket, если его ещё нет. Вызывается при старте приложения."""
        if self._bucket_ready:
            return
        try:
            if not self.client.bucket_exists(settings.minio_bucket):
                self.client.make_bucket(settings.minio_bucket)
                logger.info("MinIO bucket '%s' создан", settings.minio_bucket)
            # Разрешаем анонимное чтение, чтобы фронт мог показывать фото по ссылке
            self.client.set_bucket_policy(
                settings.minio_bucket, _public_read_policy(settings.minio_bucket)
            )
            self._bucket_ready = True
        except S3Error as exc:
            logger.error("Не удалось подготовить bucket MinIO: %s", exc)

    def upload(self, object_name: str, data: bytes, content_type: str) -> str | None:
        """Загрузить байты и вернуть публичную ссылку. None при ошибке."""
        try:
            self.ensure_bucket()
            self.client.put_object(
                settings.minio_bucket,
                object_name,
                io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )
            return (
                f"{settings.minio_public_url.rstrip('/')}/"
                f"{settings.minio_bucket}/{object_name}"
            )
        except S3Error as exc:
            logger.error("Ошибка загрузки фото '%s' в MinIO: %s", object_name, exc)
            return None


storage = PhotoStorage()
