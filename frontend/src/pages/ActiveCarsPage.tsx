import { Link } from "react-router-dom";
import { useActiveSessions } from "../api/hooks";
import { Thumb } from "../components/Thumb";
import { useState } from "react";
import { PhotoModal } from "../components/PhotoModal";
import {
  formatDateTime,
  formatDuration,
  sessionDurationSeconds,
} from "../lib/format";

export function ActiveCarsPage() {
  const { data, isLoading, isError, isFetching } = useActiveSessions();
  const [photo, setPhoto] = useState<string | null>(null);

  const cars = data ?? [];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-xl font-semibold text-slate-800">
          Машины на парковке
          {!isLoading && !isError && (
            <span className="ml-2 text-base font-normal text-slate-400">
              ({cars.length})
            </span>
          )}
        </h2>
        {isFetching && !isLoading && (
          <span className="text-xs text-slate-400">обновление…</span>
        )}
      </div>

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-3">Номер</th>
              <th className="px-4 py-3">Время въезда</th>
              <th className="px-4 py-3">На парковке</th>
              <th className="px-4 py-3">Камера въезда</th>
              <th className="px-4 py-3">Авто</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-400">
                  Загрузка…
                </td>
              </tr>
            )}

            {isError && !isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-rose-500">
                  Ошибка загрузки. Проверьте backend.
                </td>
              </tr>
            )}

            {!isLoading && !isError && cars.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-slate-400">
                  На парковке сейчас нет машин
                </td>
              </tr>
            )}

            {cars.map((s) => (
              <tr key={s.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 font-mono font-semibold tracking-wider">
                  {s.plate_number ?? "—"}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {formatDateTime(s.entry_time)}
                </td>
                <td className="px-4 py-3 font-medium text-slate-700">
                  {formatDuration(sessionDurationSeconds(s))}
                </td>
                <td className="px-4 py-3 text-slate-600">
                  {s.entry_camera_name ?? "—"}
                </td>
                <td className="px-4 py-3">
                  <Thumb url={s.vehicle_photo_url} alt="Авто" onOpen={setPhoto} />
                </td>
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

      {photo && <PhotoModal url={photo} onClose={() => setPhoto(null)} />}
    </div>
  );
}
