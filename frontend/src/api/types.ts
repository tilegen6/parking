// Типы ответов backend (соответствуют src/schemas.py)

export type Direction = "ENTRY" | "EXIT" | "UNKNOWN";

// Флаг аномалии — событие в очереди ручной проверки
export type EventFlag =
  | "low_confidence"
  | "duplicate"
  | "event_without_session"
  | "unknown_direction"
  | "possible_misread";

export interface RecognitionEvent {
  id: number;
  plate_number: string | null;
  direction: Direction;
  event_time: string;
  confidence: number | null;
  camera_id: number | null;
  camera_name: string | null;
  vehicle_photo_url: string | null;
  plate_photo_url: string | null;
  flag: EventFlag | null;
  created_at: string;
}

export interface PaginatedEvents {
  items: RecognitionEvent[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface Camera {
  id: number;
  name: string;
  ip_address: string | null;
  type: string | null;
  location: string | null;
  status: string;
  gate_id: number | null;
  created_at: string;
}

// Шлагбаумы/зоны
export interface Gate {
  id: number;
  name: string;
  zone: string | null;
  level: number;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface GateInput {
  name: string;
  zone?: string | null;
  level?: number;
  is_active?: boolean;
}

// Списки доступа
export type AccessListType = "green" | "yellow" | "red";

export interface AccessEntry {
  id: number;
  plate: string;
  list_type: AccessListType;
  gate_id: number | null; // null = на все шлагбаумы
  valid_until: string | null; // жёлтый: бесплатно до этого момента
  note: string | null;
  is_active: boolean;
  created_by_username: string | null;
  created_at: string;
  updated_at: string;
}

export interface AccessEntryInput {
  plate: string;
  list_type: AccessListType;
  gate_id?: number | null;
  valid_until?: string | null;
  note?: string | null;
  is_active?: boolean;
}

export interface Alert {
  id: number;
  kind: string;
  plate: string | null;
  gate_id: number | null;
  message: string | null;
  acknowledged: boolean;
  created_at: string;
}

export interface DashboardStats {
  events_today: number;
  last_event: {
    plate_number: string | null;
    direction: Direction;
    event_time: string;
  } | null;
  cameras_total: number;
  cameras_online: number;
}

export interface EventsFilters {
  page?: number;
  limit?: number;
  plate?: string;
  direction?: Direction | "";
  camera_id?: number;
  // Очередь ручной проверки: "any" — все с флагом, либо конкретный флаг
  flag?: EventFlag | "any" | "";
  date_from?: string;
  date_to?: string;
}

// Парковочные сессии

export type SessionStatus =
  | "active"
  | "paid"
  | "unpaid"
  | "cancelled"
  | "whitelist"
  | "auto_closed";

export interface ParkingSession {
  id: number;
  plate_number: string;
  status: SessionStatus;
  entry_time: string;
  exit_time: string | null;
  last_seen: string | null;
  duration_seconds: number | null;
  // Вычисляется бэкендом: active = сейчас минус въезд, закрытая = duration_seconds
  parked_seconds: number | null;
  price: number | null;
  paid_amount: number;
  // Старт сдвигался на последний дубль у шлагбаума (ТС-2)
  entry_adjusted: boolean;
  // Активная дольше порога (24ч) — «зависла», ручной разбор (ТС-8)
  is_stale: boolean;
  // Шлагбаум/зона сессии (null = не привязана)
  gate_id: number | null;
  // Способ проезда по спискам: green (бесплатно) / yellow (бесплатно до
  // free_until) / null (обычная платная)
  access_type: "green" | "yellow" | null;
  free_until: string | null;
  entry_event_id: number | null;
  exit_event_id: number | null;
  entry_camera_id: number | null;
  exit_camera_id: number | null;
  created_at: string;
  updated_at: string;
}

export interface PaginatedSessions {
  items: ParkingSession[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface SessionsFilters {
  page?: number;
  limit?: number;
  plate?: string;
  status?: SessionStatus | "";
  gate_id?: number;
  date_from?: string;
  date_to?: string;
}

// Тарифы (соответствует src/schemas.py TariffOut)

export interface Tariff {
  id: number;
  name: string;
  free_minutes: number;
  price_per_hour: number;
  daily_cap: number | null;
  currency: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface TariffInput {
  name: string;
  free_minutes: number;
  price_per_hour: number;
  daily_cap: number | null;
  currency?: string;
  is_active?: boolean;
}

// Платежи (соответствует src/schemas.py PaymentOut)

export type PaymentStatus = "pending" | "paid" | "failed";

export interface Payment {
  id: number;
  session_id: number;
  amount: number;
  currency: string;
  status: PaymentStatus;
  provider: string;
  provider_payment_id: string;
  provider_txn_id: string | null;
  error_code: string | null;
  pay_url: string | null;
  paid_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface BillingStats {
  revenue_today: number;
  unpaid_count: number;
  avg_parked_seconds: number | null;
}

// Kaspi (соответствует src/modules/kaspi.py)

// Статус интеграции (GET /api/v1/kaspi/info)
export interface KaspiInfo {
  payment_provider: string; // mock | kaspi
  provider_enabled: boolean;
  autopay_enabled: boolean;
}

// Ответ онлайн-протокола (GET /api/kaspi/pay, format=json)
// result: 0 ok · 1 не найдено · 2 отменён · 3 уже оплачено · 4 в обработке · 5 ошибка
export interface KaspiPayResponse {
  txn_id: string;
  result: number;
  sum?: string;
  prv_txn_id?: string;
  comment?: string;
}

// Пробное автосписание при выезде (POST /api/v1/kaspi/autopay/simulate-exit)
export interface KaspiSimulateExit {
  session_id: number;
  plate: string;
  amount: number;
  is_success: boolean;
  transaction_id: string | null;
  error_code: string | null;
  error_message: string | null;
  autopay_enabled: boolean;
}
