#!/usr/bin/env python3
"""CLI собственного CV-ANPR.

Примеры:
    # офлайн-демо на синтетике (без сети/torch):
    python recognize.py --demo --annotate

    # папка фото реальным движком:
    python recognize.py samples/ --engine easyocr --direction entry --annotate

    # видео + отправка событий в backend:
    python recognize.py clip.mp4 --video --engine easyocr \\
        --direction entry --send-to-backend http://localhost:8000
"""

from __future__ import annotations

import argparse
import os
import sys

# делаем пакет recognizer импортируемым при запуске как скрипт
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from recognizer.config import RecognizerConfig  # noqa: E402
from recognizer.pipeline import Pipeline  # noqa: E402
from recognizer.sink import AnnotatedImageSink, BackendSink, JsonSink  # noqa: E402
from recognizer.sources import ImageSource, VideoSource  # noqa: E402


def _build_sinks(cfg: RecognizerConfig) -> dict:
    sinks: dict[str, list] = {
        "json": [JsonSink(cfg.out_dir)],
        "annot": [],
        "backend": [],
    }
    if cfg.annotate:
        sinks["annot"].append(AnnotatedImageSink(cfg.out_dir))
    if cfg.send_to_backend:
        sinks["backend"].append(BackendSink(cfg.send_to_backend))
    return sinks


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Собственный CV-ANPR (own-cv-v1)")
    p.add_argument("input", nargs="?", help="файл/папка изображений или видеофайл")
    p.add_argument(
        "--video", action="store_true", help="вход — видео (трекинг + majority-vote)"
    )
    p.add_argument(
        "--demo", action="store_true", help="сгенерировать синтетику и прогнать её"
    )
    p.add_argument("--engine", choices=["template", "easyocr"], default="template")
    p.add_argument(
        "--detector",
        choices=["whole", "yolo"],
        default="whole",
        help="yolo = детекция пластины перед OCR (для грязных полнокадровых фото)",
    )
    p.add_argument("--plate-model", default=None, help="путь к YOLO-модели (.pt)")
    p.add_argument(
        "--direction", choices=["entry", "exit", "unknown"], default="unknown"
    )
    p.add_argument("--camera-name", default=None)
    p.add_argument("--confidence", type=float, default=0.85)
    p.add_argument("--fps", type=float, default=5.0, help="целевой FPS для видео")
    p.add_argument(
        "--annotate", action="store_true", help="сохранять размеченные кадры"
    )
    p.add_argument("--send-to-backend", default=None, metavar="URL")
    p.add_argument("--out", default="out", help="папка вывода (относительно cwd)")
    args = p.parse_args(argv)

    cfg = RecognizerConfig(
        engine=args.engine,
        detector=args.detector,
        plate_model=args.plate_model,
        direction=args.direction,
        camera_name=args.camera_name,
        confidence_threshold=args.confidence,
        video_fps=args.fps,
        annotate=args.annotate,
        send_to_backend=args.send_to_backend,
        out_dir=args.out,
    )

    if args.demo:
        from recognizer import synth

        demo_dir = os.path.join(cfg.out_dir, "demo_input")
        paths = synth.generate_dataset(demo_dir, n=8, seed=42, blur=1)
        print(f"Синтетика: {len(paths)} пластин -> {demo_dir}")
        args.input = demo_dir
        cfg.engine = "template"

    if not args.input:
        p.error("укажите вход (файл/папку/видео) или используйте --demo")

    pipeline = Pipeline(cfg)
    sinks = _build_sinks(cfg)
    source = (
        VideoSource(args.input, cfg.video_fps)
        if args.video
        else ImageSource(args.input)
    )
    runner = pipeline.run_video if args.video else pipeline.run_images
    events = runner(source, sinks)

    for s in sinks["json"]:
        s.close()

    ok = sum(1 for e in events if e.get("flag") == "ok")
    print(
        f"Событий: {len(events)} (валидных: {ok}, low_confidence: {len(events) - ok})"
    )
    print(f"JSON: {os.path.join(cfg.out_dir, 'events.jsonl')}")
    if cfg.annotate:
        print(f"Размеченные кадры: {os.path.join(cfg.out_dir, 'annotated')}")
    for e in events:
        plate = e["plate_number"] or "НЕ РАСПОЗНАН"
        line = f"  {e.get('frame', '?'):>16}  ->  {plate:<12}"
        line += f"  conf={e['confidence']}  [{e['flag']}]"
        if "backend_response" in e:
            br = e["backend_response"]
            line += f"  backend: {br.get('session_action', br)}"
        if "backend_error" in e:
            line += f"  backend_error: {e['backend_error']}"
        print(line)
        # при низкой уверенности показать, что ещё распозналось на кадре
        alts = [a for a in e.get("candidates", []) if a != e["plate_number"]]
        if e["flag"] == "low_confidence" and alts:
            print(f"{'':>22}прочее на кадре: {', '.join(alts[:4])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
