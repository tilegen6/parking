import type { Direction, SessionStatus } from "../api/types";

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

export function formatConfidence(value: number | null): string {
  if (value === null || value === undefined) return "—";
  return `${Math.round(value * 100)}%`;
}

export const directionLabel: Record<Direction, string> = {
  ENTRY: "Въезд",
  EXIT: "Выезд",
  UNKNOWN: "—",
};

export const directionBadgeClass: Record<Direction, string> = {
  ENTRY: "bg-emerald-100 text-emerald-700",
  EXIT: "bg-amber-100 text-amber-700",
  UNKNOWN: "bg-slate-100 text-slate-500",
};

export const sessionStatusLabel: Record<SessionStatus, string> = {
  active: "На парковке",
  unpaid: "Выехал",
  paid: "Оплачено",
  cancelled: "Отменена",
  whitelist: "Абонемент",
  auto_closed: "Закрыта авто",
};

export const sessionStatusBadgeClass: Record<SessionStatus, string> = {
  active: "bg-emerald-100 text-emerald-700",
  unpaid: "bg-amber-100 text-amber-700",
  paid: "bg-sky-100 text-sky-700",
  cancelled: "bg-slate-100 text-slate-500",
  whitelist: "bg-sky-100 text-sky-700",
  auto_closed: "bg-rose-100 text-rose-700",
};

// Флаги аномалий событий — очередь ручной проверки (ТС-2/4/5/7/9)
export const eventFlagLabel: Record<string, string> = {
  low_confidence: "низкая уверенность",
  duplicate: "дубль",
  event_without_session: "выезд без сессии",
  unknown_direction: "направление?",
  possible_misread: "похож на активный ±1",
};

export const eventFlagBadgeClass: Record<string, string> = {
  low_confidence: "bg-amber-100 text-amber-700",
  duplicate: "bg-slate-100 text-slate-500",
  event_without_session: "bg-rose-100 text-rose-700",
  unknown_direction: "bg-sky-100 text-sky-700",
  possible_misread: "bg-rose-100 text-rose-700",
};

// Длительность стоянки в человекочитаемом виде: «2 ч 5 мин», «14 мин», «45 сек».
export function formatDuration(seconds: number | null | undefined): string {
  if (seconds === null || seconds === undefined || seconds < 0) return "—";
  const total = Math.floor(seconds);
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const secs = total % 60;

  if (days > 0) return `${days} д ${hours} ч`;
  if (hours > 0) return `${hours} ч ${minutes} мин`;
  if (minutes > 0) return `${minutes} мин`;
  return `${secs} сек`;
}

// Длительность сессии в секундах. Для завершённой берём готовое значение либо
// разницу exit − entry; для активной считаем от entry_time до now.
export function sessionDurationSeconds(session: {
  entry_time: string;
  exit_time: string | null;
  duration_seconds: number | null;
}): number | null {
  if (session.duration_seconds !== null && session.duration_seconds !== undefined) {
    return session.duration_seconds;
  }
  const start = new Date(session.entry_time).getTime();
  if (Number.isNaN(start)) return null;
  const end = session.exit_time ? new Date(session.exit_time).getTime() : Date.now();
  return Math.max(0, Math.floor((end - start) / 1000));
}

export function formatAmount(value: number | null | undefined): string {
  if (value === null || value === undefined) return "—";
  return `${value.toLocaleString("ru-RU")} ₸`;
}

// Относительное время: «только что», «5 мин назад», «3 ч назад», «2 д назад».
export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const sec = Math.floor((Date.now() - t) / 1000);
  if (sec < 0) return "—";
  if (sec < 10) return "только что";
  if (sec < 60) return `${sec} сек назад`;
  const min = Math.floor(sec / 60);
  if (min < 60) return `${min} мин назад`;
  const hr = Math.floor(min / 60);
  if (hr < 24) return `${hr} ч назад`;
  return `${Math.floor(hr / 24)} д назад`;
}
