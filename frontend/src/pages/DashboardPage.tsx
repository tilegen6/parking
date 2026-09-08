import {
  useBillingStats,
  useCameras,
  useDashboardStats,
  useEvents,
} from "../api/hooks";
import { CameraHealth } from "../components/CameraHealth";
import { EventFeed } from "../components/EventFeed";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import {
  directionLabel,
  formatDateTime,
  formatDuration,
  timeAgo,
} from "../lib/format";
import { formatMoney } from "../lib/tariff";

export function DashboardPage() {
  const { data, isLoading, isError } = useDashboardStats();
  const events = useEvents({ page: 1, limit: 7 });
  const cameras = useCameras();
  const billing = useBillingStats();
  const last = data?.last_event ?? null;

  return (
    <div className="space-y-6">
      {isError && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          Не удалось загрузить статистику. Проверьте, запущен ли backend.
        </div>
      )}

      {/* HERO — последнее распознавание как настоящий KZ-знак */}
      <section className="relative overflow-hidden rounded-2xl bg-ink p-6 text-white shadow-hero lg:p-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-sky/30 blur-3xl" />
        <div className="pointer-events-none absolute -bottom-28 left-1/3 h-56 w-56 rounded-full bg-gold/10 blur-3xl" />
        <div className="relative flex flex-col gap-6 lg:flex-row lg:items-end lg:justify-between">
          <div>
            <div className="flex items-center gap-3">
              <span className="font-mono text-[11px] font-bold uppercase tracking-[0.22em] text-sky-400">
                Последнее распознавание
              </span>
              <LivePulse />
            </div>
            <div className="mt-4">
              <PlateReadout plate={last?.plate_number ?? null} size="lg" />
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3 text-sm">
              {last ? (
                <>
                  <DirectionTag direction={last.direction} />
                  <span className="text-white/55">
                    {formatDateTime(last.event_time)}
                  </span>
                  <span className="text-white/30">· {timeAgo(last.event_time)}</span>
                </>
              ) : (
                <span className="text-white/40">
                  {isLoading ? "Ожидание данных…" : "Событий ещё не было"}
                </span>
              )}
            </div>
          </div>
          <div className="text-left lg:text-right">
            <div className="font-mono text-[11px] uppercase tracking-[0.2em] text-white/35">
              поток · обновление 5с
            </div>
            <div className="mt-1 font-display text-sm text-white/70">
              Распознаватель готов к приёму
            </div>
          </div>
        </div>
      </section>

      {/* KPI */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          eyebrow="Событий сегодня"
          value={isLoading ? "…" : (data?.events_today ?? 0)}
          hint="распознаваний за сутки"
        />
        <StatTile
          eyebrow="Камеры онлайн"
          value={data?.cameras_online ?? 0}
          unit={`/ ${data?.cameras_total ?? 0}`}
          hint="устройств в сети"
        />
        <StatTile
          eyebrow="Последнее событие"
          value={last ? directionLabel[last.direction] : "—"}
          hint={last ? timeAgo(last.event_time) : "нет данных"}
        />
      </div>

      {/* Деньги (итерация 7) */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          eyebrow="Доход сегодня"
          value={
            billing.isLoading
              ? "…"
              : formatMoney(billing.data?.revenue_today ?? 0)
          }
          hint="сумма оплаченных"
        />
        <StatTile
          eyebrow="Неоплаченные"
          value={billing.data?.unpaid_count ?? 0}
          unit="сессий"
          hint="выехали без оплаты"
        />
        <StatTile
          eyebrow="Среднее время"
          value={
            billing.isLoading
              ? "…"
              : formatDuration(billing.data?.avg_parked_seconds ?? null)
          }
          hint="средняя стоянка"
        />
      </div>

      {/* Лента + камеры */}
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="lg:col-span-2">
          <EventFeed events={events.data?.items ?? []} isLoading={events.isLoading} />
        </div>
        <CameraHealth cameras={cameras.data ?? []} isLoading={cameras.isLoading} />
      </div>
    </div>
  );
}

function LivePulse() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-white/10 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wider text-emerald-300">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-emerald-400" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-400" />
      </span>
      live
    </span>
  );
}

function DirectionTag({ direction }: { direction: "ENTRY" | "EXIT" | "UNKNOWN" }) {
  const cls =
    direction === "ENTRY"
      ? "bg-emerald-400/15 text-emerald-300"
      : direction === "EXIT"
        ? "bg-amber-400/15 text-amber-300"
        : "bg-white/10 text-white/60";
  return (
    <span className={`rounded px-2 py-0.5 text-xs font-semibold ${cls}`}>
      {directionLabel[direction]}
    </span>
  );
}
