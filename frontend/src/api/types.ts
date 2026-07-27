// Типы ответов backend (соответствуют src/schemas.py)

export type Direction = "ENTRY" | "EXIT" | "UNKNOWN";

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
  date_from?: string;
  date_to?: string;
}

// Парковочные сессии

export type SessionStatus =
  | "active"
  | "paid"
  | "unpaid"
  | "cancelled"
  | "whitelist";

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
