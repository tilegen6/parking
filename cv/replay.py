"""replay.py — проигрывание событий в backend (без живой машины).

Назначение: взять sample/captured payload и отправить его в эндпоинт приёма
бэкенда ровно так, как это делает камера (multipart: XML + снимки). Позволяет
прогнать сценарии на стенде:
  * #5 въезд -> выезд
  * #6 въезд -> повторный въезд
  * #7 выезд без въезда
  * #4 дубли (повторная отправка одного события)

Запуск:
    # одиночное событие
    python replay.py samples/anpr_entry.xml --to http://localhost:8000/api/v1/hikvision/anpr-event

    # готовый сценарий (последовательность XML с паузами)
    python replay.py --scenario entry_exit --to http://localhost:8000/api/v1/hikvision/anpr-event

Сценарии используют файлы из samples/ и шлют их с заданными паузами.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import httpx

SAMPLES = Path(__file__).parent / "samples"

# имя -> список (xml_файл, пауза_до_следующего_сек)
SCENARIOS: dict[str, list[tuple[str, float]]] = {
    "entry_exit": [("anpr_entry.xml", 2.0), ("anpr_exit.xml", 0.0)],
    "repeat_entry": [("anpr_entry.xml", 2.0), ("anpr_entry.xml", 0.0)],
    "exit_no_entry": [("anpr_exit.xml", 0.0)],
    "duplicate": [("anpr_entry.xml", 1.0), ("anpr_entry.xml", 0.0)],
}


def _send(client: httpx.Client, url: str, xml_path: Path, with_photo: bool) -> None:
    xml = xml_path.read_bytes()
    files: dict[str, tuple[str, bytes, str]] = {
        "anpr.xml": ("anpr.xml", xml, "text/xml"),
    }
    if with_photo:
        # минимальный валидный JPEG-заголовок — бэкенду достаточно для загрузки
        files["licensePlatePicture.jpg"] = (
            "licensePlatePicture.jpg",
            b"\xff\xd8\xff\xe0\x00\x10JFIF" + b"\x00" * 16,
            "image/jpeg",
        )
    try:
        r = client.post(url, files=files)
        print(f"  -> {xml_path.name}: HTTP {r.status_code}  {r.text[:200]}")
    except httpx.HTTPError as exc:
        print(f"  !! {xml_path.name}: ошибка соединения: {exc}", file=sys.stderr)


def main() -> int:
    parser = argparse.ArgumentParser(description="Replay ANPR events to backend")
    parser.add_argument("xml", nargs="?", help="путь к XML события (одиночная отправка)")
    parser.add_argument(
        "--to",
        default="http://localhost:8000/api/v1/hikvision/anpr-event",
        help="URL приёма событий бэкенда",
    )
    parser.add_argument(
        "--scenario",
        choices=sorted(SCENARIOS),
        help="готовый сценарий вместо одиночного файла",
    )
    parser.add_argument("--no-photo", action="store_true", help="без вложенного снимка")
    parser.add_argument("--repeat", type=int, default=1, help="повторить N раз (для дублей)")
    args = parser.parse_args()

    with_photo = not args.no_photo
    client = httpx.Client(trust_env=False, timeout=15)

    if args.scenario:
        steps = SCENARIOS[args.scenario]
        print(f"Сценарий '{args.scenario}' -> {args.to}")
        for fname, pause in steps:
            _send(client, args.to, SAMPLES / fname, with_photo)
            if pause:
                time.sleep(pause)
        return 0

    if not args.xml:
        parser.error("укажи XML-файл или --scenario")
    path = Path(args.xml)
    if not path.exists():
        print(f"Нет файла {path}", file=sys.stderr)
        return 1

    print(f"Отправка {path.name} x{args.repeat} -> {args.to}")
    for _ in range(args.repeat):
        _send(client, args.to, path, with_photo)
    return 0


if __name__ == "__main__":
    sys.exit(main())
