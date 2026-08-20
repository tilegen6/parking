// Сохранённые подключения к живому потоку (закладки оператора).
//
// Живут в localStorage браузера, а не в БД: это личный список «куда я обычно
// подключаюсь на тесте» (телефон, RTSP камеры, демо), а не конфигурация
// парковки. Реестр боевых камер — отдельная страница «Камеры».

export interface StreamPreset {
  id: string;
  name: string;
  url: string;
  direction: "entry" | "exit";
  // Пайплайн: детектор + OCR по отдельности. version — совместимость со
  // старыми сохранёнными пресетами (готовая связка), новые их не пишут.
  detector?: string;
  engine?: string;
  version?: string;
}

const KEY = "sp_cv_presets";

// Первый запуск: демо-поток, чтобы кнопка «Подключить» было куда нажать.
const DEFAULTS: StreamPreset[] = [
  {
    id: "demo",
    name: "Демо (без камеры)",
    url: "demo",
    direction: "entry",
    engine: "template",
    detector: "whole",
  },
];

export function loadPresets(): StreamPreset[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return DEFAULTS;
    const parsed: unknown = JSON.parse(raw);
    return Array.isArray(parsed) ? (parsed as StreamPreset[]) : DEFAULTS;
  } catch {
    return DEFAULTS; // битый JSON не должен ронять панель
  }
}

export function savePresets(list: StreamPreset[]): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    // приватный режим / переполнение — переживём без сохранения
  }
}

export function newPresetId(): string {
  return Math.random().toString(36).slice(2, 10);
}

/** Прячем пароль при показе: rtsp://admin:secret@ip → rtsp://admin:•••@ip */
export function maskUrl(url: string): string {
  return url.replace(/(:\/\/[^:/@]+:)[^@]*@/, "$1•••@");
}

/** Имя по умолчанию, если оператор не вписал своё. */
export function guessName(url: string): string {
  const value = url.trim();
  if (value === "demo") return "Демо";
  try {
    const u = new URL(value);
    return `${u.protocol.replace(":", "")} · ${u.hostname}`;
  } catch {
    return value.slice(0, 24);
  }
}
