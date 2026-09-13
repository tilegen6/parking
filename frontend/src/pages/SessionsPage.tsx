import { useState } from "react";
import { Link } from "react-router-dom";
import { useSessions, useSessionStats } from "../api/hooks";
import { StatCard } from "../components/StatCard";
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
  const stats = useSessionStats();

  const resetToFirstPage = () => setPage(1);

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-800">Парковочные сессии</h2>
        {isFetching && !isLoading && (
          <span className="text-xs text-slate-400">обновление…</span>
        )}
      </div>

      {/* Карточки статистики */}
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <StatCard title="Машин на парковке" icon="🅿️">
          <span className="text-3xl font-bold">
            {stats.isLoading ? "…" : (stats.data?.cars_on_parking ?? 0)}
          </span>
        </StatCard>
        <StatCard title="Заехало сегодня" icon="⬇️">
          <span className="text-3xl font-bold text-emerald-600">
            {stats.isLoading ? "…" : (stats.data?.entered_today ?? 0)}
          </span>
        </StatCard>
        <StatCard title="Выехало сегодня" icon="⬆️">
          <span className="text-3xl font-bold text-amber-600">
            {stats.isLoading ? "…" : (stats.data?.exited_today ?? 0)}
          </span>
        </StatCard>
      </div>

      {/* Фильтры */}
      <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4">
        <Field label="Номер">
          <input
            value={plate}
            onChange={(e) => {
              setPlate(e.target.value);
              resetToFirstPage();
            }}
            placeholder="777ABC"
            className="input"
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
            <option value="ACTIVE">На парковке</option>
            <option value="COMPLETED">Завершена</option>
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
        {(plate || status || dateFrom || dateTo) && (
          <button
            onClick={() => {
              setPlate("");
              setStatus("");
              setDateFrom("");
              setDateTo("");
              resetToFirstPage();
            }}
            className="rounded-lg border border-slate-200 px-3 py-2 text-sm text-slate-600 hover:bg-slate-50"
          >
            Сбросить
          </button>
        )}
      </div>

      {/* Таблица */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
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
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
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
                <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
                  Сессий пока нет
                </td>
              </tr>
            )}

            {data?.items.map((s) => (
              <tr key={s.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-mono font-semibold tracking-wider">
                  {s.plate_number ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      sessionStatusBadgeClass[s.status]
                    }`}
                  >
                    {sessionStatusLabel[s.status]}
                  </span>
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {formatDateTime(s.entry_time)}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {s.exit_time ? formatDateTime(s.exit_time) : "—"}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {formatDuration(sessionDurationSeconds(s))}
                </td>
                <td className="px-4 py-3 text-slate-600">{formatAmount(s.amount)}</td>
                <td className="px-4 py-3 text-right">
                  <Link
                    to={`/sessions/${s.id}`}
                    className="text-sm font-medium text-brand hover:underline"
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
        <div className="flex items-center justify-between text-sm text-slate-600">
          <span>
            Всего: {data.total} · стр. {data.page} из {data.pages}
          </span>
          <div className="flex gap-2">
            <button
              disabled={page <= 1}
              onClick={() => setPage((p) => p - 1)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
            >
              ← Назад
            </button>
            <button
              disabled={page >= data.pages}
              onClick={() => setPage((p) => p + 1)}
              className="rounded-lg border border-slate-200 px-3 py-1.5 disabled:opacity-40"
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
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      {children}
    </label>
  );
}
