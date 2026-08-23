// Клиент CV-сервиса: распознавание загруженного фото номера.
// Сервис поднимается локально: `python cv/service.py` (порт 8090).

const CV_URL =
  (import.meta.env.VITE_CV_URL as string | undefined)?.replace(/\/$/, "") ??
  "http://localhost:8090";

export interface RecognizeResult {
  plate_number: string | null;
  confidence: number | null;
  flag: "ok" | "low_confidence";
  is_valid: boolean;
  candidates: string[];
  annotated_image: string; // data-URL PNG
  version?: string;
  engine?: string;
  detector?: string;
}

export interface PipelineVersion {
  name: string;
  engine: string;
  detector: string;
  label: string;
  desc: string;
}

/** Один вариант оси (детектор или OCR-движок). */
export interface PipelineOption {
  name: string;
  label: string;
  desc: string;
  available: boolean;
}

export interface PipelineCatalog {
  default: string;
  default_engine: string;
  default_detector: string;
  versions: PipelineVersion[]; // готовые связки
  detectors: PipelineOption[]; // ось «детектор»
  engines: PipelineOption[]; // ось «OCR»
}

/** Выбор пайплайна: либо готовый пресет, либо детектор+OCR по отдельности. */
export interface PipelineChoice {
  version?: string;
  engine?: string;
  detector?: string;
}

export async function recognizePlate(
  file: File,
  choice?: PipelineChoice,
): Promise<RecognizeResult> {
  const form = new FormData();
  form.append("file", file);
  if (choice?.version) form.append("version", choice.version);
  if (choice?.engine) form.append("engine", choice.engine);
  if (choice?.detector) form.append("detector", choice.detector);
  const res = await fetch(`${CV_URL}/recognize`, { method: "POST", body: form });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // тело не JSON — игнорируем
    }
    throw new Error(detail);
  }
  return (await res.json()) as RecognizeResult;
}

export async function getPipelineVersions(): Promise<PipelineCatalog> {
  const res = await fetch(`${CV_URL}/versions`);
  if (!res.ok) throw new Error(res.statusText);
  return (await res.json()) as PipelineCatalog;
}

// ── Живой поток с камеры (RTSP/телефон) ────────────────────────────────

export interface StreamStatus {
  camera: string;
  url: string;
  direction: string;
  version: string;
  running: boolean;
  error: string | null;
  frames: number;
  events: number;
  last_plate: string | null;
  opened: boolean | null;
  reconnects: number | null;
  source_error: string | null;
  /** Кадров отсеяно фильтром качества (смаз/темнота). */
  frames_dropped?: number;
  /** Сколько раз дали сигнал «открыть шлагбаум». */
  opens?: number;
  /** Треков, по которым решение так и не приняли — нужен оператор. */
  stalled?: number;
  /** Почему НЕ открыли в последний раз (stale_hit, few_votes, …). */
  last_reason?: string;
  /** Сколько машин сейчас в кадре (живых треков). */
  tracks_active?: number;
}

export interface StreamEvent {
  seq: number;
  camera: string;
  plate: string | null;
  direction: string | null;
  confidence: number | null;
  flag: string | null;
  backend_action: string | null;
  backend_error: string | null;
  time: string | null;
  /** open — был сигнал открыть шлагбаум; observe — только учёт. */
  decision?: "open" | "observe";
}

export interface StartStreamBody {
  url: string;
  direction: "entry" | "exit";
  camera_name?: string;
  version?: string;
  // Независимый выбор осей (переопределяет version):
  engine?: string;
  detector?: string;
}

async function cvJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${CV_URL}${path}`, init);
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      // тело не JSON
    }
    throw new Error(detail);
  }
  return (await res.json()) as T;
}

export function startStream(body: StartStreamBody) {
  return cvJson<{ streams: StreamStatus[] }>("/stream/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function stopStream(camera_name: string) {
  return cvJson<{ streams: StreamStatus[] }>("/stream/stop", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ camera_name }),
  });
}

export function getStreamStatus() {
  return cvJson<{ streams: StreamStatus[] }>("/stream/status");
}

export function getStreamEvents(since: number) {
  return cvJson<{ events: StreamEvent[]; last_seq: number }>(
    `/stream/events?since=${since}`,
  );
}

export function getStreamPreview(camera_name: string) {
  return cvJson<{ image: string | null; plate: string | null }>(
    `/stream/preview?camera_name=${encodeURIComponent(camera_name)}`,
  );
}

export { CV_URL };
