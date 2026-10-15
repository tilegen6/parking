#!/usr/bin/env python3
"""Прогон по казахстанским фото: OCR + маппер формата РК.

Идём напрямую через open-image-models + fast-plate-ocr (как наш прод),
а не через fast_alpr — обёртка усредняет уверенность и теряет разбивку
по символам, которая маперу как раз и нужна.
"""
from __future__ import annotations
import logging, os, sys
import cv2, numpy as np, onnxruntime as ort

ort.set_default_logger_severity(3)
logging.getLogger("open_image_models").setLevel(logging.ERROR)
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cv"))

from fast_plate_ocr import ONNXPlateRecognizer          # noqa: E402
from open_image_models import LicensePlateDetector      # noqa: E402
from recognizer.kz_format import normalize_kz           # noqa: E402

CPU = ["CPUExecutionProvider"]
folder = sys.argv[1] if len(sys.argv) > 1 else "kz_photos"
det = LicensePlateDetector(detection_model="yolo-v9-t-640-license-plate-end2end", providers=CPU)
ocr = ONNXPlateRecognizer(hub_ocr_model="global-plates-mobile-vit-v2-model", providers=CPU, device="cpu")

print(f"{'файл':<30} {'OCR':<10} {'мин.увер':>9}  {'с уверенностью':<14} {'вслепую':<10} {'статус'}")
print("-" * 100)
for name in sorted(os.listdir(folder)):
    if not name.lower().endswith((".jpg", ".jpeg", ".png")):
        continue
    img = cv2.imread(os.path.join(folder, name))
    if img is None:
        continue
    boxes = det.predict(img)
    if not boxes:
        print(f"{name[:29]:<30} {'—':<10} {'—':>9}  {'—':<14} {'—':<10} номер не найден")
        continue
    b = boxes[0].bounding_box
    crop = img[max(b.y1, 0):min(b.y2, img.shape[0]), max(b.x1, 0):min(b.x2, img.shape[1])]
    text, probs = ocr.run(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), return_confidence=True)
    raw = text.pop()
    probs = np.array(probs).ravel().tolist()
    # padding '_' в конце — его слоты в уверенность не входят
    clean = raw.replace("_", "")
    confs = probs[:len(clean)]

    guarded = normalize_kz(clean, char_confidences=confs)
    blind = normalize_kz(clean)
    flag = "" if guarded.plate == blind.plate else "  ←защита сработала"
    print(f"{name[:29]:<30} {clean:<10} {min(confs):>9.3f}  "
          f"{guarded.plate:<14} {blind.plate:<10} {guarded.status}{flag}")
