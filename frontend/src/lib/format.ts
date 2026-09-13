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
  ACTIVE: "На парковке",
  COMPLETED: "Завершена",
};

export const sessionStatusBadgeClass: Record<SessionStatus, string> = {
  ACTIVE: "bg-emerald-100 text-emerald-700",
  COMPLETED: "bg-slate-100 text-slate-500",
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
