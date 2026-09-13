import { useState } from "react";
import { useEvents } from "../api/hooks";
import { PhotoModal } from "../components/PhotoModal";
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

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-800">События распознавания</h2>
        {isFetching && !isLoading && (
          <span className="text-xs text-slate-400">обновление…</span>
        )}
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
        {(plate || direction || dateFrom || dateTo) && (
          <button
            onClick={() => {
              setPlate("");
              setDirection("");
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
              <th className="px-4 py-3">Направление</th>
              <th className="px-4 py-3">Камера</th>
              <th className="px-4 py-3">Время</th>
              <th className="px-4 py-3">Точность</th>
              <th className="px-4 py-3">Авто</th>
              <th className="px-4 py-3">Номер (фото)</th>
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
                  Событий пока нет
                </td>
              </tr>
            )}

            {data?.items.map((ev) => (
              <tr key={ev.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-mono font-semibold tracking-wider">
                  {ev.plate_number ?? "—"}
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
                <td className="px-4 py-3 text-slate-600">{ev.camera_name ?? "—"}</td>
                <td className="px-4 py-3 text-slate-600">
                  {formatDateTime(ev.event_time)}
                </td>
                <td className="px-4 py-3 text-slate-600">
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

      {photo && <PhotoModal url={photo} onClose={() => setPhoto(null)} />}
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
