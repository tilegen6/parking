#!/usr/bin/env python3
"""Бенчмарк fast-alpr на размеченном датасете.

Гоняет разные связки «детектор + OCR» по одному и тому же набору фото
и сравнивает с ground truth. Нужен, чтобы понять, даёт ли fast-alpr
выигрыш над нашей текущей связкой (yolo-v9-t-640 + global-mobile-vit-v2).

Запуск:
    .venv/bin/python bench.py ../../cv/datasets/openalpr_eu
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time

import cv2
import onnxruntime as ort

# На Apple Silicon провайдер CoreML роняет OCR-модель
# (динамические размеры не сходятся), поэтому жёстко фиксируем CPU.
ort.set_default_logger_severity(3)
logging.getLogger('open_image_models').setLevel(logging.ERROR)

from fast_alpr import ALPR  # noqa: E402

CPU_ONLY = ['CPUExecutionProvider']

# Связки, которые сравниваем. Первая — аналог того, что стоит у нас в проде.
COMBOS: list[tuple[str, str, str]] = [
    ("наш аналог", "yolo-v9-t-640-license-plate-end2end", "global-plates-mobile-vit-v2-model"),
    ("дефолт fast-alpr", "yolo-v9-t-384-license-plate-end2end", "global-plates-mobile-vit-v2-model"),
    ("крупный детектор", "yolo-v9-s-608-license-plate-end2end", "global-plates-mobile-vit-v2-model"),
    ("европейский OCR", "yolo-v9-s-608-license-plate-end2end", "european-plates-mobile-vit-v2-model"),
    ("евро OCR + t-640", "yolo-v9-t-640-license-plate-end2end", "european-plates-mobile-vit-v2-model"),
]


def normalize(text: str) -> str:
    """Канон: только буквы/цифры, верхний регистр. Так же, как в проде."""
    return "".join(ch for ch in (text or "").upper() if ch.isalnum())


def levenshtein(a: str, b: str) -> int:
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def char_accuracy(pred: str, truth: str) -> float:
    if not truth:
        return 0.0
    return max(0.0, 1.0 - levenshtein(pred, truth) / max(len(truth), len(pred), 1))


def load_labels(folder: str) -> dict[str, str]:
    """openalpr-формат: 'image x y w h PLATE' в .txt рядом с фото."""
    labels: dict[str, str] = {}
    for name in os.listdir(folder):
        if not name.endswith(".txt"):
            continue
        with open(os.path.join(folder, name), encoding="utf-8") as fh:
            for line in fh:
                parts = line.strip().split()
                if len(parts) >= 6:
                    labels[parts[0]] = normalize(parts[-1])
    return labels


def run_combo(name: str, det: str, ocr: str, folder: str, labels: dict[str, str]) -> dict:
    alpr = ALPR(
        detector_model=det,
        ocr_model=ocr,
        detector_providers=CPU_ONLY,
        ocr_providers=CPU_ONLY,
        ocr_device='cpu',
    )
    found = exact = 0
    char_sum = 0.0
    times: list[float] = []
    misses: list[tuple[str, str, str]] = []

    for img_name, truth in sorted(labels.items()):
        path = os.path.join(folder, img_name)
        if not os.path.exists(path):
            continue
        image = cv2.imread(path)
        if image is None:
            continue

        t0 = time.perf_counter()
        results = alpr.predict(image)
        times.append((time.perf_counter() - t0) * 1000)

        pred = ""
        if results and results[0].ocr is not None:
            pred = normalize(results[0].ocr.text)
            found += 1

        acc = char_accuracy(pred, truth)
        char_sum += acc
        if pred == truth:
            exact += 1
        else:
            misses.append((img_name, truth, pred or "—"))

    total = len([k for k in labels if os.path.exists(os.path.join(folder, k))])
    return {
        "name": name,
        "detector": det,
        "ocr": ocr,
        "total": total,
        "found": found,
        "exact": exact,
        "exact_pct": 100.0 * exact / total if total else 0.0,
        "detect_pct": 100.0 * found / total if total else 0.0,
        "char_pct": 100.0 * char_sum / total if total else 0.0,
        "ms_avg": sum(times) / len(times) if times else 0.0,
        "misses": misses,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("folder", help="папка с фото и .txt разметкой")
    ap.add_argument("--json", help="куда сохранить результат в JSON")
    args = ap.parse_args()

    labels = load_labels(args.folder)
    if not labels:
        print(f"Разметка не найдена в {args.folder}", file=sys.stderr)
        return 1
    print(f"Датасет: {args.folder} — {len(labels)} размеченных фото\n")

    rows = []
    for name, det, ocr in COMBOS:
        print(f"→ {name}: {det} + {ocr}")
        rows.append(run_combo(name, det, ocr, args.folder, labels))

    print("\n" + "=" * 78)
    print(f"{'Связка':<20} {'Точно':>8} {'Найдено':>9} {'Символы':>9} {'мс/фото':>9}")
    print("-" * 78)
    for r in sorted(rows, key=lambda x: -x["exact_pct"]):
        print(
            f"{r['name']:<20} {r['exact']:>3}/{r['total']:<4} "
            f"{r['exact_pct']:>6.1f}% {r['detect_pct']:>8.1f}% "
            f"{r['char_pct']:>8.1f}% {r['ms_avg']:>8.0f}"
        )
    print("=" * 78)

    best = max(rows, key=lambda x: x["exact_pct"])
    print(f"\nЛучшая связка: {best['name']}")
    print(f"  детектор: {best['detector']}")
    print(f"  OCR:      {best['ocr']}")
    if best["misses"]:
        print(f"\nОшибки лучшей связки ({len(best['misses'])}):")
        for img, truth, pred in best["misses"]:
            print(f"  {img:<18} ожидали {truth:<12} получили {pred}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=2)
        print(f"\nJSON: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
