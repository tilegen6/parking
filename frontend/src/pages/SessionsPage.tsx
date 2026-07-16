import { useState } from "react";
import { Link } from "react-router-dom";
import { useActiveSessions, useSessions } from "../api/hooks";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import type { SessionStatus, SessionsFilters } from "../api/types";
import {
  formatAmount,
  formatDateTime,
  formatDuration,
  sessionDurationSeconds,
  sessionStatusBadgeClass,
  sessionStatusLabel,
} from "../lib/format";

const PAGE_LIMIT = 20;

export function SessionsPage() {
  const [plate, setPlate] = useState("");
  const [status, setStatus] = useState<SessionStatus | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);

  const filters: SessionsFilters = {
    page,
    limit: PAGE_LIMIT,
    plate: plate || undefined,
    status: status || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };

  const { data, isLoading, isError, isFetching } = useSessions(filters);
  const active = useActiveSessions();

  const resetToFirstPage = () => setPage(1);
  const hasFilters = Boolean(plate || status || dateFrom || dateTo);

  return (
    <div className="space-y-6">
      {/* Заголовок страницы */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="eyebrow">Учёт парковки</div>
          <h2 className="font-display text-xl font-semibold text-ink">
            Парковочные сессии
          </h2>
        </div>
        {isFetching && !isLoading && (
          <span className="font-mono text-xs text-ink-500/50">обновление…</span>
        )}
      </div>

      {/* KPI */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          eyebrow="Сейчас на парковке"
          value={active.isLoading ? "…" : (active.data?.length ?? 0)}
          unit="авто"
          hint="активных сессий"
        />
        <StatTile
          eyebrow="Всего сессий"
          value={data ? data.total : "…"}
          hint={hasFilters ? "по фильтру" : "за всё время"}
        />
        <StatTile
          eyebrow="Страница"
          value={data ? data.page : "…"}
          unit={data ? `/ ${data.pages}` : undefined}
          hint={`по ${PAGE_LIMIT} на страницу`}
        />
      </div>

      {/* Фильтры */}
      <div className="card flex flex-wrap items-end gap-3 p-4">
        <Field label="Номер">
          <input
            value={plate}
            onChange={(e) => {
              setPlate(e.target.value);
              resetToFirstPage();
            }}
            placeholder="777ABC"
            className="input font-mono uppercase tracking-wide"
          />
        </Field>
        <Field label="Статус">
          <select
            value={status}
            onChange={(e) => {
              setStatus(e.target.value as SessionStatus | "");
              resetToFirstPage();
            }}
            className="input"
          >
            <option value="">Все</option>
            <option value="active">На парковке</option>
            <option value="unpaid">Выехал</option>
            <option value="paid">Оплачено</option>
            <option value="cancelled">Отменена</option>
          </select>
        </Field>
        <Field label="С даты">
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => {
              setDateFrom(e.target.value);
              resetToFirstPage();
            }}
            className="input"
          />
        </Field>
        <Field label="По дату">
          <input
            type="date"
            value={dateTo}
            onChange={(e) => {
              setDateTo(e.target.value);
              resetToFirstPage();
            }}
            className="input"
          />
        </Field>
        {hasFilters && (
          <button
            onClick={() => {
              setPlate("");
              setStatus("");
              setDateFrom("");
              setDateTo("");
              resetToFirstPage();
            }}
            className="rounded-lg border border-line px-3 py-1.5 text-sm text-ink-600 transition hover:border-sky"
          >
            Сбросить
          </button>
        )}
      </div>

      {/* Таблица */}
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">Номер</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3">Въезд</th>
              <th className="px-4 py-3">Выезд</th>
              <th className="px-4 py-3">Время стоянки</th>
              <th className="px-4 py-3">Сумма</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-ink-500/50">
                  Загрузка…
                </td>
              </tr>
            )}

            {isError && !isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-rose-500">
                  Ошибка загрузки. Проверьте backend.
                </td>
              </tr>
            )}

            {!isLoading && !isError && data?.items.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-ink-500/50">
                  Сессий пока нет
                </td>
              </tr>
            )}

            {data?.items.map((s) => (
              <tr key={s.id} className="animate-fade-up hover:bg-paper">
                <td className="px-4 py-3">
                  <PlateReadout plate={s.plate_number} size="sm" />
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      sessionStatusBadgeClass[s.status] ??
                      "bg-slate-100 text-slate-500"
                    }`}
                  >
                    {sessionStatusLabel[s.status] ?? s.status}
                  </span>
                </td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {formatDateTime(s.entry_time)}
                </td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {s.exit_time ? formatDateTime(s.exit_time) : "—"}
                </td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {formatDuration(s.parked_seconds ?? sessionDurationSeconds(s))}
                </td>
                <td className="px-4 py-3 font-mono text-ink">
                  {formatAmount(s.price)}
                </td>
                <td className="px-4 py-3 text-right">
                  <Link
                    to={`/sessions/${s.id}`}
                    className="text-sm font-medium text-sky-700 transition hover:underline"
                  >
                    Открыть
                  </Link>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Пагинация */}
      {data && data.pages > 1 && (
        <div className="flex items-center justify-between text-sm text-ink-500/70">
          <span className="font-mono">
            Всего: {data.total} · стр. {data.page} из {data.pages}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded-lg border border-line px-3 py-1.5 text-ink-600 transition hover:border-sky disabled:opacity-40 disabled:hover:border-line"
            >
              ← Назад
            </button>
            <button
              disabled={page >= data.pages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg border border-line px-3 py-1.5 text-ink-600 transition hover:border-sky disabled:opacity-40 disabled:hover:border-line"
            >
              Вперёд →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs font-medium text-ink-500/70">
      {label}
      {children}
    </label>
  );
}
