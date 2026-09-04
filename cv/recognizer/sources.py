"""Адаптеры входа -> поток Frame (единый интерфейс frames()).

- ImageSource / VideoSource — файлы (батч-обработка).
- StreamSource — живой поток: RTSP / MJPEG-http (телефон) / вебка / файл.
- DemoSource — синтетический поток для теста без камеры.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

import numpy as np

try:
    import cv2
except ImportError:  # pragma: no cover
    cv2 = None  # type: ignore[assignment]

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass
class Frame:
    image: np.ndarray
    index: int
    timestamp: datetime
    source_name: str


def _require_cv2() -> None:
    if cv2 is None:
        raise RuntimeError("Нужен opencv-python (cv2) для чтения изображений/видео")


class ImageSource:
    """Один файл или папка с изображениями. Каждое изображение = отдельный кадр."""

    def __init__(self, path: str) -> None:
        _require_cv2()
        if os.path.isdir(path):
            self.files = sorted(
                os.path.join(path, f)
                for f in os.listdir(path)
                if os.path.splitext(f)[1].lower() in IMG_EXT
            )
        else:
            self.files = [path]

    def frames(self) -> Iterator[Frame]:
        for i, f in enumerate(self.files):
            img = cv2.imread(f)
            if img is None:
                continue
            yield Frame(img, i, datetime.now(timezone.utc), os.path.basename(f))


class VideoSource:
    """Видеофайл -> выборка кадров с целевым FPS."""

    def __init__(self, path: str, target_fps: float = 5.0) -> None:
        _require_cv2()
        self.path = path
        self.target_fps = target_fps

    def frames(self) -> Iterator[Frame]:
        cap = cv2.VideoCapture(self.path)
        src_fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        step = max(1, int(round(src_fps / max(self.target_fps, 0.1))))
        name = os.path.basename(self.path)
        i = out = 0
        try:
            while True:
                ok, img = cap.read()
                if not ok:
                    break
                if i % step == 0:
                    yield Frame(img, out, datetime.now(timezone.utc), name)
                    out += 1
                i += 1
        finally:
            cap.release()


@dataclass
class StreamStatus:
    """Наблюдаемое состояние живого источника (для /stream/status)."""

    opened: bool = False
    reconnects: int = 0
    frames_read: int = 0
    last_error: str | None = None


class StreamSource:
    """Живой поток: RTSP / MJPEG-http (телефон) / индекс вебки / видеофайл.

    `cv2.VideoCapture(target)` открывает и `rtsp://…`, и `http://…/video`, и
    путь к файлу, и индекс камеры — тот же интерфейс, что у боевой камеры.
    Прореживание по стенным часам (сеть не отдаёт стабильный FPS). Живой поток
    рвётся — переподключаемся с бэкоффом. Останавливается флагом `stop()`.
    """

    def __init__(
        self,
        target: str,
        target_fps: float = 5.0,
        *,
        reconnect: bool = True,
        backoff_seconds: float = 2.0,
        name: str | None = None,
    ) -> None:
        _require_cv2()
        self.target = target
        self.target_fps = target_fps
        self.reconnect = reconnect
        self.backoff_seconds = backoff_seconds
        self.name = name or str(target)
        self.status = StreamStatus()
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def _cv_target(self):  # noqa: ANN202 — int (индекс вебки) или str (url/файл)
        return int(self.target) if str(self.target).isdigit() else self.target

    def _prepare_ffmpeg(self) -> None:
        """RTSP тянем по TCP: через VPN/NAT UDP-медиа теряется и поток рвётся.

        OpenCV читает эти опции из env при открытии VideoCapture (backend ffmpeg).
        stimeout — таймаут сокета (мкс), чтобы не висеть вечно на мёртвом потоке.
        """
        if str(self.target).lower().startswith("rtsp://"):
            os.environ["OPENCV_FFMPEG_CAPTURE_OPTIONS"] = (
                "rtsp_transport;tcp|stimeout;5000000"
            )

    def _sleep(self, seconds: float) -> None:
        """Спим маленькими шагами, чтобы быстро реагировать на stop()."""
        waited = 0.0
        while waited < seconds and not self._stop:
            time.sleep(min(0.2, seconds - waited))
            waited += 0.2

    def frames(self) -> Iterator[Frame]:
        interval = 1.0 / max(self.target_fps, 0.1)
        self._prepare_ffmpeg()
        while not self._stop:
            cap = cv2.VideoCapture(self._cv_target())
            if not cap.isOpened():
                cap.release()
                self.status.opened = False
                self.status.last_error = "не удалось открыть источник"
                if not self.reconnect:
                    return
                self.status.reconnects += 1
                self._sleep(self.backoff_seconds)
                continue

            self.status.opened = True
            self.status.last_error = None
            last = 0.0
            try:
                while not self._stop:
                    ok, img = cap.read()
                    if not ok:
                        self.status.last_error = "поток прервался"
                        break
                    now = time.monotonic()
                    if now - last < interval:
                        continue
                    last = now
                    self.status.frames_read += 1
                    yield Frame(
                        img,
                        self.status.frames_read,
                        datetime.now(timezone.utc),
                        self.name,
                    )
            finally:
                cap.release()

            self.status.opened = False
            if not self.reconnect:
                return
            self.status.reconnects += 1
            self._sleep(self.backoff_seconds)


class DemoSource:
    """Синтетический «поток»: номера появляются и уходят — без камеры/сети.

    Позволяет проверить весь путь (источник → пайплайн → бэкенд → сессия → UI)
    ещё до подключения телефона/камеры. Работает с движком `template` (v0).
    Каждая «машина» держится `dwell` кадров, затем `gap` пустых кадров (уезжает),
    после чего трек закрывается и эмитится ровно одно событие.
    """

    def __init__(
        self,
        target_fps: float = 5.0,
        *,
        dwell: int = 12,
        gap: int = 8,
        size: tuple[int, int] = (480, 640),
        seed: int = 42,
    ) -> None:
        _require_cv2()
        import random

        self.target_fps = target_fps
        self.dwell = dwell
        self.gap = gap
        self.size = size
        self.name = "demo"
        self.status = StreamStatus(opened=True)
        self._rng = random.Random(seed)
        self._stop = False

    def stop(self) -> None:
        self._stop = True

    def _canvas(self) -> np.ndarray:
        h, w = self.size
        # светлый фон: template-OCR читает чёрные глифы на белом (пустой кадр = «нет номера»)
        return np.full((h, w, 3), 235, dtype=np.uint8)

    def _scene(self, plate_img: np.ndarray) -> np.ndarray:
        canvas = self._canvas()
        ph, pw = plate_img.shape[:2]
        scale = min((self.size[1] * 0.6) / pw, (self.size[0] * 0.3) / ph, 3.0)
        resized = cv2.resize(plate_img, (int(pw * scale), int(ph * scale)))
        rh, rw = resized.shape[:2]
        y = (self.size[0] - rh) // 2
        x = (self.size[1] - rw) // 2
        canvas[y : y + rh, x : x + rw] = resized
        return canvas

    def frames(self) -> Iterator[Frame]:
        from . import synth

        interval = 1.0 / max(self.target_fps, 0.1)
        blank = self._canvas()
        idx = 0
        while not self._stop:
            plate = synth.random_kz_plate(self._rng)
            scene = self._scene(synth.render_plate(plate))
            for _ in range(self.dwell):
                if self._stop:
                    return
                idx += 1
                self.status.frames_read = idx
                yield Frame(scene.copy(), idx, datetime.now(timezone.utc), self.name)
                time.sleep(interval)
            for _ in range(self.gap):
                if self._stop:
                    return
                idx += 1
                self.status.frames_read = idx
                yield Frame(blank.copy(), idx, datetime.now(timezone.utc), self.name)
                time.sleep(interval)
