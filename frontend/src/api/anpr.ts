// Отправка ANPR-события в backend — тот же эндпоинт, что у камеры/CV.
// Используется страницей «Симулятор КПП» для прогона сценариев въезд/выезд.

import { api } from "./client";
import type { Direction } from "./types";

export interface AnprResult {
  status: string;
  id: number;
  plate_number: string | null;
  session_action: string; // created | updated_last_seen | closed | duplicate_exit | ...
  session_id: number | null;
}

export interface AnprInput {
  plateNumber: string;
  direction: Direction;
  confidence: number;
  deviceName?: string;
  /**
   * Время события. По умолчанию — сейчас. Для теста можно задать въезд «задним
   * числом» (backend берёт entry_time из dateTime) — так на парковке появляется
   * машина, у которой уже «набежал» долг.
   */
  at?: Date;
}

export function sendAnprEvent(input: AnprInput): Promise<AnprResult> {
  const { at, ...rest } = input;
  return api.post<AnprResult>("/api/v1/hikvision/anpr-event", {
    ...rest,
    dateTime: (at ?? new Date()).toISOString(),
  });
}
