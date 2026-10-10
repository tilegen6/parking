# Песочница fast-alpr

Отдельный стенд для проверки библиотеки [`fast-alpr`](https://pypi.org/project/fast-alpr/).
**В прод-контур не входит** — ни backend, ни `cv/` его не импортируют.

## Главный вывод

`fast-alpr` — это обёртка над теми же двумя библиотеками, что у нас уже стоят:
`open-image-models` (детектор YOLO-v9) + `fast-plate-ocr` (OCR mobile-vit-v2).
Своих моделей у неё нет. Выигрыша в точности над нашей текущей связкой не даёт.

Замер на `cv/datasets/openalpr_eu` (25 фото с разметкой):

| Связка | Точных | Найдено | Символы | мс/фото |
|---|---|---|---|---|
| yolo-v9-**t-640** + global (наш аналог) | 88.0% | 100% | 98.3% | 33 |
| yolo-v9-**t-384** + global (дефолт lib) | 88.0% | 100% | 98.3% | **16** |
| yolo-v9-**s-608** + global | 88.0% | 100% | 98.3% | 52 |
| yolo-v9-s-608 + **european** | 76.0% | 100% | 95.3% | 52 |
| yolo-v9-t-640 + **european** | 76.0% | 100% | 94.7% | 33 |

Что из этого следует:
1. **Размер детектора не влияет на точность** — но t-384 вдвое быстрее t-640 при том же
   результате. Кандидат на ускорение прода.
2. **Европейский OCR хуже глобального** на 12 п.п. — переключаться не надо.
3. **Детекция 100% во всех связках.** Все ошибки — исключительно OCR.
4. Все 3 ошибки одного класса: `O`↔`0` и `X`↔`4`, причём при уверенности 0.97.
   Порог по confidence такие ошибки не отсечёт — нужна проверка по формату номера.

## Две ловушки на macOS

1. `pip install fast-alpr[onnx-gpu]` на Apple Silicon **ставит обычный CPU-onnxruntime**.
   Экстра `onnx-gpu` тянет `onnxruntime-gpu`, а он только под CUDA (Linux/Windows).
   Ошибки не будет — просто GPU не появится.
2. `ocr_device="auto"` выбирает **CoreML, и OCR-модель на нём падает**:
   `Size (9) of dimension (2) is not in allowed range (8..8)`.
   Лечится принудительным CPU:
   ```python
   ALPR(detector_providers=["CPUExecutionProvider"],
        ocr_providers=["CPUExecutionProvider"], ocr_device="cpu")
   ```

## Запуск

```bash
python3.13 -m venv .venv
.venv/bin/pip install "fast-alpr[onnx-gpu]" fastapi "uvicorn[standard]" python-multipart
```

Веб-стенд (загрузить фото → JSON):
```bash
.venv/bin/python app.py      # http://localhost:8099
```

Бенчмарк на размеченном наборе:
```bash
.venv/bin/python bench.py ../../cv/datasets/openalpr_eu --json results_eu.json
```

Разметка в формате openalpr: `.txt` рядом с фото, строка `имя x y w h НОМЕР`.
