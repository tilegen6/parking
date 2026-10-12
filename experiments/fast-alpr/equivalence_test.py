#!/usr/bin/env python3
"""Доказательство: fast-alpr — обёртка, а не отдельная (до)обученная модель.

Гоняем одни и те же фото двумя путями:
  A) через fast_alpr.ALPR
  B) напрямую через open_image_models + fast_plate_ocr — ровно так, как это
     делает наш прод (cv/recognizer/detect.py + cv/recognizer/ocr.py)

Если модели у fast-alpr свои (дообученные), числа разойдутся.
Если это обёртка — совпадут бит в бит.
"""

from __future__ import annotations

import logging
import os
import sys

import cv2
import numpy as np
import onnxruntime as ort

ort.set_default_logger_severity(3)
logging.getLogger("open_image_models").setLevel(logging.ERROR)

from fast_alpr import ALPR  # noqa: E402
from fast_plate_ocr import ONNXPlateRecognizer  # noqa: E402
from open_image_models import LicensePlateDetector  # noqa: E402

CPU = ["CPUExecutionProvider"]
DET = "yolo-v9-t-640-license-plate-end2end"   # то же, что в cv/recognizer/detect.py:116
OCR = "global-plates-mobile-vit-v2-model"     # то же, что в cv/recognizer/ocr.py:164


def path_a(alpr: ALPR, img: np.ndarray) -> list[tuple]:
    """Через обёртку fast-alpr."""
    out = []
    for r in alpr.predict(img):
        bb = r.detection.bounding_box
        out.append(
            (r.ocr.text if r.ocr else None,
             float(r.ocr.confidence) if r.ocr else None,
             float(r.detection.confidence),
             (bb.x1, bb.y1, bb.x2, bb.y2))
        )
    return out


def path_b(det: LicensePlateDetector, ocr: ONNXPlateRecognizer, img: np.ndarray) -> list[tuple]:
    """Напрямую через две библиотеки — как в нашем проде."""
    out = []
    for d in det.predict(img):
        bb = d.bounding_box
        x1, y1 = max(bb.x1, 0), max(bb.y1, 0)
        x2, y2 = min(bb.x2, img.shape[1]), min(bb.y2, img.shape[0])
        crop = img[y1:y2, x1:x2]
        gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
        text, probs = ocr.run(gray, return_confidence=True)
        text = text.pop().replace("_", "")
        out.append((text, float(np.mean(probs)), float(d.confidence), (bb.x1, bb.y1, bb.x2, bb.y2)))
    return out


def main() -> int:
    folder = sys.argv[1] if len(sys.argv) > 1 else "../../cv/datasets/openalpr_eu"
    images = sorted(f for f in os.listdir(folder) if f.lower().endswith((".jpg", ".png")))

    alpr = ALPR(detector_model=DET, ocr_model=OCR,
                detector_providers=CPU, ocr_providers=CPU, ocr_device="cpu")
    det = LicensePlateDetector(detection_model=DET, providers=CPU)
    ocr = ONNXPlateRecognizer(hub_ocr_model=OCR, providers=CPU, device="cpu")

    same = diff = 0
    print(f"{'фото':<16} {'fast-alpr':<12} {'напрямую':<12} {'conf A':>9} {'conf B':>9}  итог")
    print("-" * 74)
    for name in images:
        img = cv2.imread(os.path.join(folder, name))
        if img is None:
            continue
        a, b = path_a(alpr, img), path_b(det, ocr, img)
        ok = (a == b)
        same, diff = same + ok, diff + (not ok)
        ta = a[0][0] if a else "—"
        tb = b[0][0] if b else "—"
        ca = f"{a[0][1]:.6f}" if a and a[0][1] is not None else "—"
        cb = f"{b[0][1]:.6f}" if b else "—"
        print(f"{name:<16} {ta:<12} {tb:<12} {ca:>9} {cb:>9}  {'идентично' if ok else 'РАЗЛИЧИЕ'}")

    print("-" * 74)
    print(f"Совпало полностью: {same} из {same + diff}")
    if diff == 0:
        print("\nВЫВОД: результаты совпадают бит в бит, включая confidence до 6 знаков.")
        print("fast-alpr не содержит собственных весов — это обёртка над теми же моделями.")
    else:
        print(f"\nВНИМАНИЕ: {diff} расхождений — модели НЕ идентичны, надо разбираться.")
    return 0 if diff == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
