// TanStack Query хуки для данных backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, buildQuery } from "./client";
import type {
  BillingStats,
  Camera,
  DashboardStats,
  EventsFilters,
  PaginatedEvents,
  PaginatedSessions,
  ParkingSession,
  Payment,
  SessionsFilters,
  Tariff,
  TariffInput,
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
        `/api/v1/parking-sessions${buildQuery({ ...filters })}`,
      ),
    // Автообновление — список сессий меняется по мере въезда/выезда машин
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  });
}

export function useActiveSessions() {
  return useQuery({
    queryKey: ["sessions", "active"],
    queryFn: () => api.get<ParkingSession[]>("/api/v1/parking-sessions/active"),
    // Машины на парковке обновляем чаще — это «живой» экран
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  });
}

export function useSession(id: number) {
  return useQuery({
    queryKey: ["session", id],
    queryFn: () => api.get<ParkingSession>(`/api/v1/parking-sessions/${id}`),
    enabled: Number.isFinite(id),
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

// Тарифы

export function useTariffs() {
  return useQuery({
    queryKey: ["tariffs"],
    queryFn: () => api.get<Tariff[]>("/api/v1/tariffs"),
  });
}

export function useCreateTariff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TariffInput) =>
      api.post<Tariff>("/api/v1/tariffs", payload),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tariffs"] }),
  });
}

export function useUpdateTariff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { id: number; patch: Partial<TariffInput> }) =>
      api.put<Tariff>(`/api/v1/tariffs/${args.id}`, args.patch),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tariffs"] }),
  });
}

export function useDeleteTariff() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: number) => api.del(`/api/v1/tariffs/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["tariffs"] }),
  });
}

// Платежи

export function useUnpaidSessions() {
  return useQuery({
    queryKey: ["sessions", "unpaid"],
    queryFn: () => api.get<ParkingSession[]>("/api/v1/parking-sessions/unpaid"),
    refetchInterval: 5000,
    placeholderData: (prev) => prev,
  });
}

export function useBillingStats() {
  return useQuery({
    queryKey: ["billing-stats"],
    queryFn: () => api.get<BillingStats>("/api/v1/dashboard/billing"),
    refetchInterval: 5000,
  });
}

export function useCreatePayment() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) =>
      api.post<Payment>("/api/v1/payments/create", { session_id: sessionId }),
    onSuccess: () => qc.invalidateQueries(),
  });
}

/** Подтверждение оплаты через webhook (в MVP — вместо реального провайдера). */
export function useConfirmPaymentMock() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (providerPaymentId: string) =>
      api.post<Payment>("/api/v1/payments/webhook", {
        provider_payment_id: providerPaymentId,
      }),
    onSuccess: () => qc.invalidateQueries(),
  });
}
