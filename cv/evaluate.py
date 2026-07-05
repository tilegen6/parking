#!/usr/bin/env python3
"""Оценка распознавателя на датасете с разметкой.

Считает: точность точного совпадения (exact), среднюю посимвольную точность
(char) и долю кадров, где номер вообще найден (detection).

Источники разметки (--labels-from):
  filename   номер = имя файла без расширения (123ABC02.jpg -> 123ABC02)
  openalpr   .txt рядом с фото (формат строки: image x y w h PLATE)
  csv        CSV-файл из --labels (колонки: filename,plate)

Примеры:
    python evaluate.py datasets/openalpr_eu --labels-from openalpr \
        --engine easyocr --detector yolo
    python evaluate.py out/kz_demo --labels-from filename --engine template
"""

from __future__ import annotations

import argparse
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recognizer.config import RecognizerConfig  # noqa: E402
from recognizer.metrics import char_accuracy, is_exact  # noqa: E402
from recognizer.pipeline import Pipeline  # noqa: E402
from recognizer.sources import IMG_EXT, ImageSource  # noqa: E402

EVAL_DESC = "Оценка CV-распознавателя на датасете"


def _list_images(path: str) -> list[str]:
    if os.path.isfile(path):
        return [path]
    return sorted(
        os.path.join(path, f)
        for f in os.listdir(path)
        if os.path.splitext(f)[1].lower() in IMG_EXT
    )


def load_labels(path: str, labels_from: str, labels_csv: str | None) -> dict[str, str]:
    """basename изображения -> эталонный номер."""
    labels: dict[str, str] = {}
    if labels_from == "csv" or labels_csv:
        with open(labels_csv or path, encoding="utf-8") as f:
            for row in csv.reader(f):
                if len(row) >= 2 and row[0].strip().lower() != "filename":
                    labels[os.path.basename(row[0].strip())] = row[1].strip()
        return labels

    for img in _list_images(path):
        base = os.path.basename(img)
        stem, _ = os.path.splitext(base)
        if labels_from == "filename":
            labels[base] = stem
        elif labels_from == "openalpr":
            txt = os.path.join(os.path.dirname(img), stem + ".txt")
            if os.path.exists(txt):
                line = open(txt, encoding="utf-8").readline().strip()
                parts = line.split("\t") if "\t" in line else line.split()
                if parts:
                    labels[base] = parts[-1]
    return labels


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=EVAL_DESC)
    p.add_argument("input", help="папка с изображениями (или один файл)")
    p.add_argument("--engine", choices=["template", "easyocr"], default="easyocr")
    p.add_argument("--detector", choices=["whole", "yolo"], default="whole")
    p.add_argument("--plate-model", default=None)
    p.add_argument("--confidence", type=float, default=0.85)
    p.add_argument(
        "--labels-from", choices=["filename", "openalpr", "csv"], default="openalpr"
    )
    p.add_argument("--labels", default=None, help="путь к CSV (filename,plate)")
    p.add_argument("--limit", type=int, default=0, help="ограничить число фото (0=все)")
    args = p.parse_args(argv)

    labels = load_labels(args.input, args.labels_from, args.labels)
    if not labels:
        p.error("разметка не найдена — проверьте --labels-from / --labels")

    cfg = RecognizerConfig(
        engine=args.engine,
        detector=args.detector,
        plate_model=args.plate_model,
        confidence_threshold=args.confidence,
    )
    pipeline = Pipeline(cfg)
    source = ImageSource(args.input)

    n = exact = detected = 0
    char_sum = 0.0
    print(f"\n{'ФАЙЛ':<16} {'ЭТАЛОН':<12} {'РАСПОЗНАНО':<12} {'EXACT':<6} CHAR%")
    print("-" * 60)
    for frame in source.frames():
        gt = labels.get(frame.source_name)
        if gt is None:
            continue
        if args.limit and n >= args.limit:
            break
        res = pipeline.process_frame(frame.image)
        pred = res.plate if res and res.plate else ""
        ok = is_exact(pred, gt)
        ca = char_accuracy(pred, gt)
        n += 1
        exact += int(ok)
        detected += int(bool(pred))
        char_sum += ca
        mark = "✓" if ok else " "
        print(
            f"{frame.source_name:<16} {gt:<12} {pred or '—':<12} "
            f"{mark:<6} {ca * 100:5.1f}"
        )

    if n == 0:
        print("Нет фото с разметкой.")
        return 1
    print("-" * 60)
    print(f"Фото с разметкой:        {n}")
    print(f"Точное совпадение:       {exact}/{n}  = {exact / n * 100:.1f}%")
    print(f"Средняя посимв. точность: {char_sum / n * 100:.1f}%")
    print(f"Номер найден (detection): {detected}/{n}  = {detected / n * 100:.1f}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
