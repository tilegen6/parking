import { Link, useParams } from "react-router-dom";
import type { ReactNode } from "react";
import { useSession } from "../api/hooks";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import {
  formatAmount,
  formatDateTime,
  formatDuration,
  sessionDurationSeconds,
  sessionStatusBadgeClass,
  sessionStatusLabel,
} from "../lib/format";

export function SessionDetailPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const { data, isLoading, isError, isFetching } = useSession(id);

  const duration = data
    ? (data.parked_seconds ?? sessionDurationSeconds(data))
    : null;

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-4">
          <Link
            to="/sessions"
            className="rounded-lg border border-line px-3 py-1.5 text-sm text-ink-600 transition hover:border-sky"
          >
            ← Все сессии
          </Link>
          <div>
            <div className="eyebrow">Парковочная сессия</div>
            <h2 className="font-display text-xl font-semibold text-ink">
              Сессия #{Number.isFinite(id) ? id : "—"}
            </h2>
          </div>
        </div>
        {isFetching && !isLoading && (
          <span className="font-mono text-xs text-ink-500/50">обновление…</span>
        )}
      </div>

      {isLoading && (
        <div className="card p-12 text-center text-sm text-ink-500/50">
          Загрузка…
        </div>
      )}

      {isError && !isLoading && (
        <div className="card p-12 text-center text-sm text-rose-500">
          Не удалось загрузить сессию. Проверьте backend.
        </div>
      )}

      {data && (
        <>
          {/* Карточка-«паспорт» сессии: номер как KZ-знак + статус */}
          <div className="card animate-fade-up p-6">
            <div className="flex flex-wrap items-center gap-4">
              <PlateReadout plate={data.plate_number} size="lg" />
              <span
                className={`rounded px-3 py-1 text-sm font-medium ${
                  sessionStatusBadgeClass[data.status] ??
                  "bg-slate-100 text-slate-500"
                }`}
              >
                {sessionStatusLabel[data.status] ?? data.status}
              </span>
            </div>

            <div className="mt-6 border-t border-line pt-6">
              <dl className="grid grid-cols-1 gap-x-8 gap-y-5 sm:grid-cols-2 lg:grid-cols-3">
                <Row label="Время въезда" value={formatDateTime(data.entry_time)} mono />
                <Row
                  label="Время выезда"
                  value={
                    data.exit_time
                      ? formatDateTime(data.exit_time)
                      : "— (на парковке)"
                  }
                  mono={!!data.exit_time}
                />
                <Row label="Время стоянки" value={formatDuration(duration)} />
                <Row
                  label="Камера въезда"
                  value={data.entry_camera_id ? `#${data.entry_camera_id}` : "—"}
                  mono
                />
                <Row
                  label="Камера выезда"
                  value={data.exit_camera_id ? `#${data.exit_camera_id}` : "—"}
                  mono
                />
                <Row
                  label="Последняя отметка"
                  value={data.last_seen ? formatDateTime(data.last_seen) : "—"}
                  mono={!!data.last_seen}
                />
              </dl>
            </div>
          </div>

          {/* KPI: длительность и сумма крупными числами */}
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <StatTile
              eyebrow="Время на парковке"
              value={formatDuration(duration)}
              hint={data.status === "active" ? "идёт сейчас" : "от въезда до выезда"}
            />
            <StatTile
              eyebrow="Сумма к оплате"
              value={formatAmount(data.price)}
              hint={data.price != null ? "начислено за стоянку" : "ещё не рассчитана"}
            />
          </div>
        </>
      )}
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: ReactNode;
  mono?: boolean;
}) {
  return (
    <div>
      <dt className="eyebrow">{label}</dt>
      <dd className={`mt-1 text-ink ${mono ? "font-mono text-sm" : ""}`}>{value}</dd>
    </div>
  );
}
