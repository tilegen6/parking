// TanStack Query хуки для данных backend.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, buildQuery } from "./client";
import type {
  BillingStats,
  Camera,
  DashboardStats,
  EventsFilters,
  KaspiInfo,
  KaspiPayResponse,
  KaspiSimulateExit,
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

// ТС-7: оператор вручную назначает направление событию UNKNOWN
export function useAssignDirection() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({
      eventId,
      direction,
    }: {
      eventId: number;
      direction: "ENTRY" | "EXIT";
    }) =>
      api.post<{
        id: number;
        direction: string;
        session_action: string;
        session_id: number | null;
      }>(`/api/v1/recognition/events/${eventId}/direction`, { direction }),
    onSuccess: () => qc.invalidateQueries(),
  });
}

// ТС-8: ручная отмена зависшей/ошибочной сессии
export function useCancelSession() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) =>
      api.post<ParkingSession>(`/api/v1/parking-sessions/${sessionId}/cancel`, {}),
    onSuccess: () => qc.invalidateQueries(),
  });
}

// Kaspi (онлайн-протокол провайдера + автосписание)

/** Статус интеграции Kaspi (активный провайдер, включённые режимы). */
export function useKaspiInfo() {
  return useQuery({
    queryKey: ["kaspi-info"],
    queryFn: () => api.get<KaspiInfo>("/api/v1/kaspi/info"),
  });
}

/** Эмулирует запрос Kaspi «check» — какая сумма к оплате по номеру авто. */
export function useKaspiCheck() {
  return useMutation({
    mutationFn: (args: { plate: string; txnId: string }) =>
      api.get<KaspiPayResponse>(
        `/api/kaspi/pay${buildQuery({
          command: "check",
          account: args.plate,
          txn_id: args.txnId,
          sum: "0",
          format: "json",
        })}`,
      ),
  });
}

/** Эмулирует запрос Kaspi «pay» — провести оплату (идемпотентно по txn_id). */
export function useKaspiPay() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (args: { plate: string; sum: number; txnId: string }) =>
      api.get<KaspiPayResponse>(
        `/api/kaspi/pay${buildQuery({
          command: "pay",
          account: args.plate,
          txn_id: args.txnId,
          sum: args.sum.toFixed(2),
          txn_date: new Date()
            .toISOString()
            .replace(/[-:T]/g, "")
            .slice(0, 14),
          format: "json",
        })}`,
      ),
    onSuccess: () => qc.invalidateQueries(),
  });
}

/** Пробное автосписание при выезде (Kaspi AutomaticPayments) — только DEBUG. */
export function useKaspiSimulateExit() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (sessionId: number) =>
      api.post<KaspiSimulateExit>("/api/v1/kaspi/autopay/simulate-exit", {
        session_id: sessionId,
      }),
    onSuccess: () => qc.invalidateQueries(),
  });
}
