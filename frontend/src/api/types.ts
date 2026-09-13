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

export type SessionStatus = "ACTIVE" | "COMPLETED";

export interface ParkingSession {
  id: number;
  plate_number: string | null;
  status: SessionStatus;
  entry_time: string;
  exit_time: string | null;
  // Длительность стоянки в секундах. Для активных сессий backend может не
  // присылать значение — тогда считаем от entry_time на клиенте.
  duration_seconds: number | null;
  entry_camera_name: string | null;
  exit_camera_name: string | null;
  vehicle_photo_url: string | null;
  plate_photo_url: string | null;
  amount: number | null;
  created_at: string;
}

export interface PaginatedSessions {
  items: ParkingSession[];
  total: number;
  page: number;
  limit: number;
  pages: number;
}

export interface SessionStats {
  cars_on_parking: number;
  entered_today: number;
  exited_today: number;
}

export interface SessionsFilters {
  page?: number;
  limit?: number;
  plate?: string;
  status?: SessionStatus | "";
  date_from?: string;
  date_to?: string;
}
