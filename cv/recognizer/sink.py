"""Приёмники результата: JSON-лог, размеченные кадры, отправка в backend."""

from __future__ import annotations

import json
import os

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

try:
    import httpx
except ImportError:  # pragma: no cover
    httpx = None  # type: ignore[assignment]


class JsonSink:
    """Пишет по одной JSON-строке на событие в out_dir/events.jsonl."""

    def __init__(self, out_dir: str) -> None:
        os.makedirs(out_dir, exist_ok=True)
        self.path = os.path.join(out_dir, "events.jsonl")
        self._f = open(self.path, "w", encoding="utf-8")

    def write(self, record: dict) -> None:
        self._f.write(json.dumps(record, ensure_ascii=False) + "\n")
        self._f.flush()

    def close(self) -> None:
        self._f.close()


class AnnotatedImageSink:
    """Сохраняет кадр с нарисованным боксом и распознанным номером."""

    def __init__(self, out_dir: str) -> None:
        self.dir = os.path.join(out_dir, "annotated")
        os.makedirs(self.dir, exist_ok=True)
        self._n = 0

    def write(self, image, plate, box=None) -> None:
        if cv2 is None:
            return
        img = image.copy()
        if box:
            x1, y1, x2, y2 = box
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 0), 2)
        cv2.putText(
            img, plate or "?", (10, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 200, 0), 2
        )
        path = os.path.join(self.dir, f"{self._n:04d}_{plate or 'none'}.png")
        cv2.imwrite(path, img)
        self._n += 1


class BackendSink:
    """POST события в существующий backend-эндпоинт приёма ANPR."""

    def __init__(self, url: str) -> None:
        if httpx is None:
            raise RuntimeError("Нужен httpx для отправки в backend")
        self.endpoint = url.rstrip("/") + "/api/v1/hikvision/anpr-event"

    def send(self, backend_json: dict) -> dict:
        r = httpx.post(self.endpoint, json=backend_json, timeout=15)
        r.raise_for_status()
        return r.json()
