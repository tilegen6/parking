#!/usr/bin/env python3
"""Песочница fast-alpr: загружаешь фото — получаешь JSON распознавания.

Отдельный стенд, в прод-контур не входит. Нужен, чтобы вручную прогонять
реальные фото с объекта и смотреть, что выдаёт модель.

Запуск:
    .venv/bin/python app.py          # http://localhost:8099
"""

from __future__ import annotations

import base64
import io
import logging
import os
import sys
import time

import cv2
import numpy as np
import onnxruntime as ort
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# На Apple Silicon CoreML роняет OCR-модель — жёстко фиксируем CPU.
ort.set_default_logger_severity(3)
logging.getLogger("open_image_models").setLevel(logging.ERROR)

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "cv"))

from fast_alpr import ALPR  # noqa: E402
from fast_plate_ocr import ONNXPlateRecognizer  # noqa: E402
from open_image_models import LicensePlateDetector  # noqa: E402
from recognizer.kz_format import normalize_kz  # noqa: E402

CPU_ONLY = ["CPUExecutionProvider"]

DETECTORS = [
    "yolo-v9-t-384-license-plate-end2end",
    "yolo-v9-t-512-license-plate-end2end",
    "yolo-v9-t-640-license-plate-end2end",
    "yolo-v9-s-608-license-plate-end2end",
]
OCRS = [
    "global-plates-mobile-vit-v2-model",
    "european-plates-mobile-vit-v2-model",
    "argentinian-plates-cnn-model",
]

app = FastAPI(title="fast-alpr sandbox")
_raw_cache: dict[tuple[str, str], tuple] = {}


def get_raw(detector: str, ocr: str) -> tuple:
    """Прямая пара моделей — нужна ради посимвольной уверенности."""
    key = (detector, ocr)
    if key not in _raw_cache:
        _raw_cache[key] = (
            LicensePlateDetector(detection_model=detector, providers=CPU_ONLY),
            ONNXPlateRecognizer(hub_ocr_model=ocr, providers=CPU_ONLY, device="cpu"),
        )
    return _raw_cache[key]

# Готовые фото из репозитория — чтобы проверить стенд, не ища файлы на диске.
_SAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "kz_photos")
if os.path.isdir(_SAMPLES_DIR):
    app.mount("/samples", StaticFiles(directory=_SAMPLES_DIR), name="samples")
# Реальные казахстанские фото: классический, новый формат, старый советский.
SAMPLES = [
    "photo_2026-09-04 02.27.22.jpeg",   # 040 BS 01  — классический короткий
    "photo_2026-09-04 02.27.21.jpeg",   # AQ 003 01  — новый формат
    "2026-09-04 02.29.05.jpg",          # A 724 CBM  — старый советский
    "photo_2026-09-04 02.26.51.jpeg",   # 237 BLM 01 — образец
]
_cache: dict[tuple[str, str], ALPR] = {}


def get_alpr(detector: str, ocr: str) -> ALPR:
    """Модели тяжёлые — держим по одному экземпляру на связку."""
    key = (detector, ocr)
    if key not in _cache:
        _cache[key] = ALPR(
            detector_model=detector,
            ocr_model=ocr,
            detector_providers=CPU_ONLY,
            ocr_providers=CPU_ONLY,
            ocr_device="cpu",
        )
    return _cache[key]


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    det_opts = "".join(
        f'<option value="{d}"{" selected" if "t-640" in d else ""}>{d}</option>'
        for d in DETECTORS
    )
    ocr_opts = "".join(f'<option value="{o}">{o}</option>' for o in OCRS)
    import json as _json
    return (
        PAGE.replace("{{DET}}", det_opts)
        .replace("{{OCR}}", ocr_opts)
        .replace("__SAMPLES__", _json.dumps(SAMPLES))
    )


@app.post("/recognize")
async def recognize(
    file: UploadFile = File(...),
    detector: str = Form(DETECTORS[2]),
    ocr: str = Form(OCRS[0]),
) -> JSONResponse:
    raw = await file.read()
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        return JSONResponse({"error": "не удалось прочитать изображение"}, status_code=400)

    alpr = get_alpr(detector, ocr)
    t0 = time.perf_counter()
    results = alpr.predict(image)
    elapsed = (time.perf_counter() - t0) * 1000

    plates = []
    for r in results:
        d, o = r.detection, r.ocr
        bb = d.bounding_box
        plates.append(
            {
                "plate": (o.text if o else None),
                "plate_canon": "".join(c for c in (o.text or "").upper() if c.isalnum())
                if o
                else None,
                "ocr_confidence": round(float(o.confidence), 4) if o else None,
                "detector_confidence": round(float(d.confidence), 4),
                "box": {"x1": bb.x1, "y1": bb.y1, "x2": bb.x2, "y2": bb.y2},
                "box_size_px": {"w": bb.x2 - bb.x1, "h": bb.y2 - bb.y1},
            }
        )

    # Посимвольная уверенность + приведение к формату РК.
    det_m, ocr_m = get_raw(detector, ocr)
    for entry, d in zip(plates, alpr.predict(image)):
        bb = d.detection.bounding_box
        crop = image[max(bb.y1, 0):min(bb.y2, image.shape[0]),
                     max(bb.x1, 0):min(bb.x2, image.shape[1])]
        if crop.size == 0:
            continue
        text, probs = ocr_m.run(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), return_confidence=True)
        clean = text.pop().replace("_", "")
        confs = np.array(probs).ravel().tolist()[: len(clean)]
        fmt = normalize_kz(clean, char_confidences=confs)
        entry["char_confidence"] = [round(float(c), 3) for c in confs]
        entry["confidence_min"] = round(float(min(confs)), 4) if confs else None
        entry["kz"] = {
            "plate": fmt.plate,
            "format": fmt.format_name,
            "region": fmt.region,
            "corrections": fmt.corrections,
            "status": fmt.status,
            "trusted": fmt.is_trusted,
        }

    annotated = alpr.draw_predictions(image.copy())
    ok, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 85])
    preview = base64.b64encode(buf.tobytes()).decode() if ok else None

    return JSONResponse(
        {
            "filename": file.filename,
            "image_size": {"w": image.shape[1], "h": image.shape[0]},
            "detector_model": detector,
            "ocr_model": ocr,
            "elapsed_ms": round(elapsed, 1),
            "plates_found": len(plates),
            "plates": plates,
            "_preview_b64": preview,
        }
    )


PAGE = """<!doctype html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>fast-alpr — песочница</title><style>
*{box-sizing:border-box}
body{margin:0;font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;
background:#0f1216;color:#e6e9ef}
.wrap{max-width:1100px;margin:0 auto;padding:28px 20px 60px}
h1{font-size:21px;margin:0 0 4px}
.sub{color:#8b95a5;font-size:13px;margin-bottom:22px}
.controls{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
label{display:block;font-size:12px;color:#8b95a5;margin-bottom:5px}
select{background:#171c23;color:#e6e9ef;border:1px solid #2a323d;border-radius:8px;
padding:9px 11px;font-size:13px;min-width:290px}
#drop{border:2px dashed #2f3846;border-radius:14px;padding:44px 20px;text-align:center;
cursor:pointer;transition:.15s;background:#131820}
#drop:hover,#drop.over{border-color:#4a9eff;background:#161d27}
#drop b{color:#4a9eff}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:18px;margin-top:22px}
@media(max-width:860px){.grid{grid-template-columns:1fr}}
.card{background:#131820;border:1px solid #232b36;border-radius:12px;overflow:hidden}
.card h2{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:#8b95a5;
margin:0;padding:12px 15px;border-bottom:1px solid #232b36}
.card .body{padding:15px}
img{max-width:100%;border-radius:8px;display:block}
pre{margin:0;font:12px/1.55 ui-monospace,SFMono-Regular,Menlo,monospace;
white-space:pre-wrap;word-break:break-word;color:#c8d3e0}
.hit{display:flex;align-items:baseline;gap:10px;padding:10px 12px;background:#0d1117;
border:1px solid #232b36;border-radius:9px;margin-bottom:9px}
.plate{font:700 19px ui-monospace,Menlo,monospace;letter-spacing:1.5px;color:#fff}
.conf{font-size:12px;color:#8b95a5;margin-left:auto}
.good{color:#3fb950}.mid{color:#d29922}.bad{color:#f85149}
.hint{color:#8b95a5;font-size:12px;margin-top:10px}
.busy{color:#4a9eff}
.samples{margin-top:12px;font-size:12px;color:#8b95a5}
.samples button{background:#1b2husb;background:#1b222c;color:#c8d3e0;border:1px solid #2a323d;
border-radius:7px;padding:5px 11px;font-size:12px;cursor:pointer;margin-right:6px}
.samples button:hover{border-color:#4a9eff;color:#fff}
</style></head><body><div class="wrap">
<h1>fast-alpr — песочница</h1>
<div class="sub">Отдельный стенд для проверки модели. В прод-контур не входит.</div>
<div class="controls">
  <div><label>Детектор</label><select id="det">{{DET}}</select></div>
  <div><label>OCR</label><select id="ocr">{{OCR}}</select></div>
</div>
<div id="drop">Перетащи фото сюда или <b>выбери файл</b>
  <div class="hint">jpg / png · можно несколько раз подряд</div>
</div>
<input type="file" id="inp" accept="image/*" hidden>
<div class="samples">Или готовые примеры: <span id="samples"></span></div>
<div class="grid">
  <div class="card"><h2>Что увидела модель</h2><div class="body" id="vis">
    <span class="hint">пока пусто</span></div></div>
  <div class="card"><h2>JSON-ответ</h2><div class="body">
    <pre id="out">пока пусто</pre></div></div>
</div></div>
<script>
const SAMPLES=__SAMPLES__;
document.getElementById('samples').innerHTML=SAMPLES.map(s=>
  `<button onclick="runSample('${s}')">${s}</button>`).join('');
async function runSample(name){
  const r=await fetch('/samples/'+name);const b=await r.blob();
  send(new File([b],name,{type:b.type||'image/jpeg'}));
}
const drop=document.getElementById('drop'),inp=document.getElementById('inp'),
out=document.getElementById('out'),vis=document.getElementById('vis');
drop.onclick=()=>inp.click();
drop.ondragover=e=>{e.preventDefault();drop.classList.add('over')};
drop.ondragleave=()=>drop.classList.remove('over');
drop.ondrop=e=>{e.preventDefault();drop.classList.remove('over');
  if(e.dataTransfer.files[0])send(e.dataTransfer.files[0])};
inp.onchange=()=>inp.files[0]&&send(inp.files[0]);

function cls(c){return c>=.9?'good':c>=.7?'mid':'bad'}

async function send(file){
  out.textContent='распознаю…';out.className='busy';
  vis.innerHTML='<span class="hint">обработка…</span>';
  const fd=new FormData();
  fd.append('file',file);
  fd.append('detector',document.getElementById('det').value);
  fd.append('ocr',document.getElementById('ocr').value);
  try{
    const r=await fetch('/recognize',{method:'POST',body:fd});
    const j=await r.json();
    const prev=j._preview_b64;delete j._preview_b64;
    out.className='';
    out.textContent=JSON.stringify(j,null,2);
    let html='';
    if(j.plates&&j.plates.length){
      for(const p of j.plates){
        const k=p.kz||{};
        const st={ok:'good',corrected:'mid',ambiguous:'bad',unknown_format:'bad'}[k.status]||'bad';
        html+=`<div class="hit"><span class="plate">${k.plate||p.plate_canon||'—'}</span>
          <span class="conf" style="margin-left:8px"><b class="${st}">${
          k.format||'формат не распознан'}</b>${k.corrections?` · правок ${k.corrections}`:''}${
          k.region?` · регион ${k.region}`:''}</span></div>
        <div class="hit"><span style="font-size:12px;color:#8b95a5">сырой OCR: <b>${
          p.plate_canon||'—'}</b> · мин. уверенность по символу <b class="${
          cls(p.confidence_min)}">${((p.confidence_min||0)*100).toFixed(1)}%</b></span>
          <span class="conf">OCR <b class="${cls(p.ocr_confidence)}">${
          (p.ocr_confidence*100).toFixed(1)}%</b> · детектор <b class="${
          cls(p.detector_confidence)}">${(p.detector_confidence*100).toFixed(1)}%</b></span></div>`;
      }
    }else{html='<div class="hint">номер не найден</div>';}
    if(prev)html+=`<img src="data:image/jpeg;base64,${prev}">`;
    html+=`<div class="hint">${j.elapsed_ms} мс · ${j.image_size.w}×${j.image_size.h}</div>`;
    vis.innerHTML=html;
  }catch(err){out.className='';out.textContent='Ошибка: '+err;}
}
</script></body></html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8099, log_level="warning")
