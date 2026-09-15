#!/usr/bin/env python3
"""Скачать подвыборку датасета openalpr/benchmarks (фото номеров + разметка).

Это публичный набор реальных фото машин с эталонными номерами (ground truth):
рядом с каждым фото лежит .txt, последнее поле — номер.

Пример:
    python scripts/fetch_openalpr.py --region eu --n 25 --out datasets/openalpr_eu
    python evaluate.py datasets/openalpr_eu --labels-from openalpr \
        --engine easyocr --detector yolo
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.request

API = "https://api.github.com/repos/openalpr/benchmarks/contents/endtoend/{region}"
RAW = "https://raw.githubusercontent.com/openalpr/benchmarks/master/endtoend/{region}/{name}"


def _ensure_ssl() -> None:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
    from recognizer.util import ensure_ssl_certs

    ensure_ssl_certs()


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Скачать датасет openalpr/benchmarks")
    p.add_argument("--region", choices=["eu", "us", "br"], default="eu")
    p.add_argument("--n", type=int, default=25, help="сколько фото скачать")
    p.add_argument("--out", default=None, help="папка назначения")
    args = p.parse_args(argv)

    _ensure_ssl()
    out = args.out or f"datasets/openalpr_{args.region}"
    os.makedirs(out, exist_ok=True)

    with urllib.request.urlopen(API.format(region=args.region)) as r:
        listing = json.load(r)
    images = [
        x["name"]
        for x in listing
        if x["name"].lower().endswith((".jpg", ".jpeg", ".png"))
    ][: args.n]

    for i, name in enumerate(images, 1):
        stem = os.path.splitext(name)[0]
        for fn in (name, stem + ".txt"):
            try:
                urllib.request.urlretrieve(
                    RAW.format(region=args.region, name=fn), os.path.join(out, fn)
                )
            except Exception as e:  # noqa: BLE001
                print(f"  пропуск {fn}: {e}")
        print(f"  [{i}/{len(images)}] {name}")

    print(f"Готово: {len(images)} фото с разметкой -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
