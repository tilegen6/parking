// TanStack Query хуки для данных backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, buildQuery } from "./client";
import type {
  Camera,
  DashboardStats,
  EventsFilters,
  PaginatedEvents,
  PaginatedSessions,
  ParkingSession,
  SessionStats,
  SessionsFilters,
} from "./types";

export function useEvents(filters: EventsFilters) {
  return useQuery({
    queryKey: ["events", filters],
    queryFn: () =>
      api.get<PaginatedEvents>(
        `/api/v1/recognition/events${buildQuery({ ...filters })}`,
      ),
    // Автообновление таблицы каждые 5 секунд — админ видит новые машины почти сразу
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  });
}

export function useDashboardStats() {
  return useQuery({
    queryKey: ["dashboard-stats"],
    queryFn: () => api.get<DashboardStats>("/api/v1/dashboard/stats"),
    refetchInterval: 5000,
  });
}

export function useCameras() {
  return useQuery({
    queryKey: ["cameras"],
    queryFn: () => api.get<Camera[]>("/api/v1/cameras"),
    refetchInterval: 10000,
  });
}

// Парковочные сессии

export function useSessions(filters: SessionsFilters) {
  return useQuery({
    queryKey: ["sessions", filters],
    queryFn: () =>
      api.get<PaginatedSessions>(
        `/api/v1/sessions${buildQuery({ ...filters })}`,
      ),
    // Автообновление — список сессий меняется по мере въезда/выезда машин
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  });
}

export function useActiveSessions() {
  return useQuery({
    queryKey: ["sessions", "active"],
    queryFn: () => api.get<ParkingSession[]>("/api/v1/sessions/active"),
    // Машины на парковке обновляем чаще — это «живой» экран
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  });
}

export function useSession(id: number) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => api.get<ParkingSession>(`/api/v1/sessions/${id}`),
    enabled: Number.isFinite(id),
    refetchInterval: 5000,
  });
}

export function useSessionStats() {
  return useQuery({
    queryKey: ["sessions", "stats"],
    queryFn: () => api.get<SessionStats>("/api/v1/sessions/stats"),
    refetchInterval: 5000,
  });
}

export function useCreateCamera() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: Partial<Camera>) =>
      api.post<Camera>("/api/v1/cameras", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["cameras"] }),
  });
}
