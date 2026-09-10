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

export { CV_URL };
