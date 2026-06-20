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
