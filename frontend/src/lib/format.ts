import type { Direction } from "../api/types";

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
