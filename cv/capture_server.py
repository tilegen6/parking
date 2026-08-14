"""capture_server.py — приёмник событий камеры Hikvision (integration lab).

Назначение: навести камеру (HTTP listening / Alarm Server) на этот сервер и
снять РЕАЛЬНЫЙ payload — чтобы зафиксировать формат и косяки для backend.
Закрывает задачу Integration/Hikvision #3 «Проверить реальные payload события».

Поведение:
  * принимает POST на любой путь;
  * сохраняет каждое событие в captures/<timestamp>/:
      - raw.bin        — сырое тело запроса как есть;
      - headers.json   — заголовки + метаданные;
      - event.xml/json — текстовая часть (если найдена);
      - <part>.jpg ...  — бинарные части (снимки);
      - summary.json   — извлечённые поля (номер/направление/время...);
  * ВСЕГДА отвечает 200 OK — иначе при включённом ANR камера зациклит событие.

Запуск:
    pip install -r requirements.txt
    python capture_server.py --port 8088 --out captures/
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import uvicorn
from fastapi import FastAPI, Request, Response

OUT_DIR = Path("captures")


def _ts() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%S-%f")[:-3]


def _strip_ns(tag: str) -> str:
    return tag.split("}", 1)[-1]


def _xml_summary(raw: bytes) -> dict[str, str]:
    """Быстрая выжимка ключевых полей из XML (без зависимостей на backend)."""
    wanted = {
        "licenseplate": "plate_number",
        "direction": "direction",
        "datetime": "event_time",
        "confidencelevel": "confidence",
        "channelname": "camera_name",
        "eventtype": "event_type",
    }
    found: dict[str, str] = {}
    try:
        root = ET.fromstring(raw)
    except ET.ParseError:
        return found
    for el in root.iter():
        key = _strip_ns(el.tag).lower()
        if key in wanted and key not in found and el.text and el.text.strip():
            found[wanted[key]] = el.text.strip()
    return found


def _save_capture(out: Path, headers: dict[str, str], body: bytes) -> dict[str, object]:
    cap_dir = out / _ts()
    cap_dir.mkdir(parents=True, exist_ok=True)

    (cap_dir / "raw.bin").write_bytes(body)
    (cap_dir / "headers.json").write_text(
        json.dumps(headers, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    content_type = headers.get("content-type", "")
    summary: dict[str, object] = {"content_type": content_type, "size": len(body)}
    parts_saved: list[str] = []

    # multipart разбираем вручную, чтобы сохранить ВСЕ части как на проводе
    if content_type.startswith("multipart/form-data") and "boundary=" in content_type:
        boundary = content_type.split("boundary=", 1)[1].strip().strip('"')
        delim = b"--" + boundary.encode()
        for idx, chunk in enumerate(body.split(delim)):
            chunk = chunk.strip(b"\r\n")
            if not chunk or chunk == b"--":
                continue
            head, _, payload = chunk.partition(b"\r\n\r\n")
            head_txt = head.decode("latin-1", "replace")
            name = f"part{idx}"
            for line in head_txt.splitlines():
                if "filename=" in line:
                    name = line.split("filename=", 1)[1].strip().strip('";')
                    break
            if payload:
                (cap_dir / name).write_bytes(payload)
                parts_saved.append(name)
                if payload.lstrip().startswith(b"<"):
                    summary.update(_xml_summary(payload))
                    (cap_dir / "event.xml").write_bytes(payload)
                elif payload.lstrip().startswith(b"{"):
                    (cap_dir / "event.json").write_bytes(payload)
    elif body.lstrip().startswith(b"<"):
        (cap_dir / "event.xml").write_bytes(body)
        summary.update(_xml_summary(body))
    elif body.lstrip().startswith(b"{"):
        (cap_dir / "event.json").write_bytes(body)

    summary["parts"] = parts_saved
    summary["dir"] = str(cap_dir)
    (cap_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return summary


def build_app(out: Path) -> FastAPI:
    app = FastAPI(title="Hikvision Capture Server", docs_url=None, redoc_url=None)

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.api_route("/{full_path:path}", methods=["POST", "PUT"])
    async def capture(request: Request, full_path: str) -> Response:
        body = await request.body()
        headers = {k.lower(): v for k, v in request.headers.items()}
        summary = _save_capture(out, headers, body)
        print(
            f"[{_ts()}] capture: plate={summary.get('plate_number')} "
            f"dir={summary.get('direction')} type={summary.get('event_type')} "
            f"bytes={summary.get('size')} -> {summary.get('dir')}",
            flush=True,
        )
        # Камера ждёт 200, иначе ANR зациклит. Тело не важно.
        return Response(status_code=200, content="OK")

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Hikvision ANPR capture server")
    parser.add_argument("--port", type=int, default=8088)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--out", default=str(OUT_DIR), help="каталог для дампов")
    args = parser.parse_args()

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    print(f"Capture server on http://{args.host}:{args.port}  ->  {out}/", flush=True)
    uvicorn.run(build_app(out), host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    sys.exit(main())
