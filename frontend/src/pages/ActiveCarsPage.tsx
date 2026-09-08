import { Link } from "react-router-dom";
import { useActiveSessions } from "../api/hooks";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import { formatDateTime, formatDuration, timeAgo } from "../lib/format";

export function ActiveCarsPage() {
  const { data, isLoading, isError, isFetching } = useActiveSessions();
  const cars = data ?? [];

  return (
    <div className="space-y-6">
      {/* Заголовок раздела */}
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="eyebrow">КПП · парковка</div>
          <h2 className="font-display text-xl font-semibold text-ink">
            Машины на парковке
          </h2>
        </div>
        {isFetching && !isLoading && (
          <span className="inline-flex items-center gap-2 font-mono text-[11px] uppercase tracking-wider text-ink-500/50">
            <span className="relative flex h-1.5 w-1.5">
              <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-sky" />
              <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-sky" />
            </span>
            обновление…
          </span>
        )}
      </div>

      {/* KPI — сколько машин сейчас на территории */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          eyebrow="Сейчас на парковке"
          value={isLoading ? "…" : cars.length}
          unit="авто"
          hint={isError ? "нет данных" : "активных сессий"}
        />
      </div>

      {/* Таблица активных сессий */}
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">Номер</th>
              <th className="px-4 py-3">Время въезда</th>
              <th className="px-4 py-3">На парковке</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={4} className="px-4 py-14 text-center text-ink-500/50">
                  Загрузка…
                </td>
              </tr>
            )}

            {isError && !isLoading && (
              <tr>
                <td colSpan={4} className="px-4 py-14 text-center text-rose-500">
                  Ошибка загрузки. Проверьте backend.
                </td>
              </tr>
            )}

            {!isLoading && !isError && cars.length === 0 && (
              <tr>
                <td colSpan={4} className="px-4 py-14 text-center text-ink-500/50">
                  На парковке сейчас нет машин
                </td>
              </tr>
            )}

            {cars.map((s) => (
              <tr key={s.id} className="animate-fade-up hover:bg-paper">
                <td className="px-4 py-3">
                  <PlateReadout plate={s.plate_number} size="sm" />
                </td>
                <td className="px-4 py-3">
                  <div className="font-mono text-ink-600">
                    {formatDateTime(s.entry_time)}
                  </div>
                  <div className="mt-0.5 text-xs text-ink-500/50">
                    {timeAgo(s.entry_time)}
                  </div>
                </td>
                <td className="px-4 py-3 font-mono font-medium text-emerald-700">
                  {formatDuration(s.parked_seconds)}
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
    </div>
  );
}
