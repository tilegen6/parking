#!/usr/bin/env python3
"""Загрузка РАЗМЕЧЕННЫХ фото номеров через публичный mobile-API platesmania.

Эндпоинт (без ключа):
    https://platesmania.com/mobile/api_photo_test.php?nomer=<plate>

Это ПОИСК ПО НОМЕРУ: на вход — номер, на выход — фото авто с этим номером.
Значит сам запрашиваемый номер и есть метка -> сохраняем файл как <НОМЕР>_<i>.jpg
и пишем labels.csv. Получается готовый размеченный набор для:
    python evaluate.py datasets/platesmania --labels-from filename \
        --engine fastplate --detector plate

ВАЖНО (правовое): фотографии — пользовательский контент (чужой копирайт).
Используй для ЛОКАЛЬНОГО теста/оценки/исследования, НЕ для перепубликации.
Запрашивай вежливо (--delay), не перебирай массово несуществующие номера.

Примеры:
    python scripts/fetch_platesmania.py --plates a001aa22,o777oo77
    python scripts/fetch_platesmania.py --plates-file plates.txt --size original
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import time

import httpx

API = "https://platesmania.com/mobile/api_photo_test.php"
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
)


def _safe(s: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", s).upper()


def _load_plates(args) -> list[str]:
    if args.plates:
        return [x.strip() for x in args.plates.split(",") if x.strip()]
    with open(args.plates_file, encoding="utf-8") as f:
        return [ln.strip() for ln in f if ln.strip() and not ln.startswith("#")]


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description="Размеченные фото номеров через mobile-API platesmania"
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--plates", help="номера через запятую")
    g.add_argument(
        "--plates-file", help="файл: по одному номеру в строке (# — коммент)"
    )
    p.add_argument("--out", default="datasets/platesmania", help="папка вывода")
    p.add_argument("--size", choices=["small", "medium", "original"], default="medium")
    p.add_argument("--delay", type=float, default=1.5, help="пауза между номерами, сек")
    p.add_argument(
        "--max-per-plate", type=int, default=2, help="сколько фото брать на номер"
    )
    args = p.parse_args(argv)

    plates = _load_plates(args)
    os.makedirs(args.out, exist_ok=True)
    labels_path = os.path.join(args.out, "labels.csv")
    new_file = not os.path.exists(labels_path)
    client = httpx.Client(
        headers={"User-Agent": UA}, timeout=25.0, follow_redirects=True
    )

    found = 0
    downloaded = 0
    with open(labels_path, "a", newline="", encoding="utf-8") as lf:
        w = csv.writer(lf)
        if new_file:
            w.writerow(["file", "plate", "make", "model", "date", "source"])
        for plate in plates:
            try:
                data = client.get(API, params={"nomer": plate}).json()
            except Exception as e:  # noqa: BLE001
                print(f"  {plate}: запрос упал: {e}")
                time.sleep(args.delay)
                continue
            cars = data.get("cars") or []
            if data.get("error") or not cars:
                print(f"  {plate}: не найдено")
                time.sleep(args.delay)
                continue
            found += 1
            for j, car in enumerate(cars[: args.max_per_plate]):
                url = (car.get("photo") or {}).get(args.size)
                if not url:
                    continue
                fn = f"{_safe(plate)}_{j}.jpg"
                make = car.get("make", "")
                model = car.get("model", "")
                date = car.get("date", "")
                try:
                    img = client.get(url).content
                    if len(img) < 1024:  # хотлинк-заглушка (напр. avto-nomer.ru)
                        print(f"  {plate}: пропуск {url} (заглушка, {len(img)}b)")
                        continue
                    with open(os.path.join(args.out, fn), "wb") as imgf:
                        imgf.write(img)
                    w.writerow([fn, _safe(plate), make, model, date, url])
                    downloaded += 1
                    print(f"  {plate}: {fn}  ({make} {model})")
                except Exception as e:  # noqa: BLE001
                    print(f"  {plate}: не скачал {url}: {e}")
            time.sleep(args.delay)

    print(f"\nномеров найдено: {found}/{len(plates)}, фото скачано: {downloaded}")
    print(f"метки: {labels_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
