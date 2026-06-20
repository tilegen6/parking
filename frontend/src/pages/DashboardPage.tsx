import { useDashboardStats } from "../api/hooks";
import { StatCard } from "../components/StatCard";
import {
  directionBadgeClass,
  directionLabel,
  formatDateTime,
} from "../lib/format";

export function DashboardPage() {
  const { data, isLoading, isError } = useDashboardStats();

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-slate-800">Дашборд</h2>

      {isError && (
        <div className="rounded-lg bg-rose-50 p-4 text-sm text-rose-700">
          Не удалось загрузить статистику. Проверьте, запущен ли backend.
        </div>
      )}

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatCard title="Событий сегодня" icon="🚗">
          <span className="text-3xl font-bold">
            {isLoading ? "…" : (data?.events_today ?? 0)}
          </span>
        </StatCard>

        <StatCard title="Последнее распознавание" icon="🔢">
          {data?.last_event ? (
            <div className="space-y-1">
              <div className="font-mono text-2xl font-bold tracking-wider">
                {data.last_event.plate_number ?? "—"}
              </div>
              <div className="flex items-center gap-2 text-sm">
                <span
                  className={`rounded px-2 py-0.5 text-xs font-medium ${
                    directionBadgeClass[data.last_event.direction]
                  }`}
                >
                  {directionLabel[data.last_event.direction]}
                </span>
                <span className="text-slate-500">
                  {formatDateTime(data.last_event.event_time)}
                </span>
              </div>
            </div>
          ) : (
            <span className="text-slate-400">{isLoading ? "…" : "Нет данных"}</span>
          )}
        </StatCard>

        <StatCard title="Статус камер" icon="📷">
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-emerald-600">
              {data?.cameras_online ?? 0}
            </span>
            <span className="text-slate-400">/ {data?.cameras_total ?? 0} online</span>
          </div>
        </StatCard>
      </div>
    </div>
  );
}
