import { useState } from "react";
import { useEvents } from "../api/hooks";
import { PhotoModal } from "../components/PhotoModal";
import { PlateReadout } from "../components/PlateReadout";
import { StatTile } from "../components/StatTile";
import { Thumb } from "../components/Thumb";
import type { Direction, EventsFilters } from "../api/types";
import {
  directionBadgeClass,
  directionLabel,
  formatConfidence,
  formatDateTime,
} from "../lib/format";

const PAGE_LIMIT = 20;

export function EventsPage() {
  const [plate, setPlate] = useState("");
  const [direction, setDirection] = useState<Direction | "">("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [page, setPage] = useState(1);
  const [photo, setPhoto] = useState<string | null>(null);

  const filters: EventsFilters = {
    page,
    limit: PAGE_LIMIT,
    plate: plate || undefined,
    direction: direction || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
  };

  const { data, isLoading, isError, isFetching } = useEvents(filters);

  const resetToFirstPage = () => setPage(1);

  const hasFilters = Boolean(plate || direction || dateFrom || dateTo);
  const shown = data?.items.length ?? 0;

  return (
    <div className="space-y-6">
      {/* Заголовок */}
      <div className="flex items-end justify-between gap-4">
        <div>
          <div className="eyebrow">Журнал</div>
          <h2 className="font-display text-xl font-semibold text-ink">
            События распознавания
          </h2>
          <p className="mt-1 text-sm text-ink-500/70">
            Каждый проезд через КПП — с номером, направлением и кадрами камеры.
          </p>
        </div>
        {isFetching && !isLoading && (
          <span className="font-mono text-xs text-ink-500/50">обновление…</span>
        )}
      </div>

      {/* KPI */}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        <StatTile
          eyebrow="Всего событий"
          value={data ? data.total : "…"}
          hint={hasFilters ? "по текущему фильтру" : "за всё время"}
        />
        <StatTile
          eyebrow="Страница"
          value={data ? data.page : "…"}
          unit={data ? `/ ${data.pages}` : undefined}
          hint={`по ${PAGE_LIMIT} на страницу`}
        />
        <StatTile
          eyebrow="Показано"
          value={isLoading ? "…" : shown}
          hint="строк на этой странице"
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
        <Field label="Направление">
          <select
            value={direction}
            onChange={(e) => {
              setDirection(e.target.value as Direction | "");
              resetToFirstPage();
            }}
            className="input"
          >
            <option value="">Все</option>
            <option value="ENTRY">Въезд</option>
            <option value="EXIT">Выезд</option>
            <option value="UNKNOWN">Неизвестно</option>
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
              setDirection("");
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
              <th className="px-4 py-3">Направление</th>
              <th className="px-4 py-3">Камера</th>
              <th className="px-4 py-3">Время</th>
              <th className="px-4 py-3">Точность</th>
              <th className="px-4 py-3">Авто</th>
              <th className="px-4 py-3">Номер (фото)</th>
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
                  Событий пока нет
                </td>
              </tr>
            )}

            {data?.items.map((ev) => (
              <tr key={ev.id} className="animate-fade-up hover:bg-paper">
                <td className="px-4 py-3">
                  <PlateReadout plate={ev.plate_number} size="sm" />
                </td>
                <td className="px-4 py-3">
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      directionBadgeClass[ev.direction]
                    }`}
                  >
                    {directionLabel[ev.direction]}
                  </span>
                </td>
                <td className="px-4 py-3 text-ink-500/70">{ev.camera_name ?? "—"}</td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {formatDateTime(ev.event_time)}
                </td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {formatConfidence(ev.confidence)}
                </td>
                <td className="px-4 py-3">
                  <Thumb url={ev.vehicle_photo_url} alt="Авто" onOpen={setPhoto} />
                </td>
                <td className="px-4 py-3">
                  <Thumb url={ev.plate_photo_url} alt="Номер" onOpen={setPhoto} />
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

      {photo && <PhotoModal url={photo} onClose={() => setPhoto(null)} />}
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
