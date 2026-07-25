// Оценка стоимости парковки на фронте — ЗЕРКАЛО backend calculate_price (ТЗ §3.4).
// Реальная сумма всегда считается на бэкенде; здесь только превью для Студии.

import type { Tariff } from "../api/types";

type PriceRules = Pick<Tariff, "free_minutes" | "price_per_hour" | "daily_cap">;

export function estimatePrice(
  durationSeconds: number,
  tariff: PriceRules,
): number {
  const durationMinutes = durationSeconds / 60;
  const billableMinutes = durationMinutes - tariff.free_minutes;
  if (billableMinutes <= 0) return 0;

  const dayMinutes = 24 * 60;
  const fullDays = Math.floor(billableMinutes / dayMinutes);
  const remMinutes = billableMinutes - fullDays * dayMinutes;
  const remHours = Math.ceil(remMinutes / 60);

  const dayCost = (hours: number): number => {
    const cost = hours * tariff.price_per_hour;
    return tariff.daily_cap != null ? Math.min(cost, tariff.daily_cap) : cost;
  };

  const total = fullDays * dayCost(24) + dayCost(remHours);
  return Math.round(total * 100) / 100;
}

export function formatMoney(amount: number | null, currency = "KZT"): string {
  if (amount == null) return "—";
  return `${Math.round(amount).toLocaleString("ru-RU")} ${currency}`;
}
