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

export async function recognizePlate(
  file: File,
  version?: string,
): Promise<RecognizeResult> {
  const form = new FormData();
  form.append("file", file);
  if (version) form.append("version", version);
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

export async function getPipelineVersions(): Promise<{
  default: string;
  versions: PipelineVersion[];
}> {
  const res = await fetch(`${CV_URL}/versions`);
  if (!res.ok) throw new Error(res.statusText);
  return (await res.json()) as { default: string; versions: PipelineVersion[] };
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
}

export interface StartStreamBody {
  url: string;
  direction: "entry" | "exit";
  camera_name?: string;
  version?: string;
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
