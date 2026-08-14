import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useSession } from "../api/hooks";
import { PhotoModal } from "../components/PhotoModal";
import type { ReactNode } from "react";
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
  const [photo, setPhoto] = useState<string | null>(null);

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-3">
        <Link
          to="/sessions"
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50"
        >
          ← Все сессии
        </Link>
        <h2 className="text-xl font-semibold text-slate-800">
          Сессия #{Number.isFinite(id) ? id : "—"}
        </h2>
        {isFetching && !isLoading && (
          <span className="text-xs text-slate-400">обновление…</span>
        )}
      </div>

      {isLoading && (
        <div className="rounded-xl border border-slate-200 bg-white p-8 text-center text-slate-400">
          Загрузка…
        </div>
      )}

      {isError && !isLoading && (
        <div className="rounded-lg bg-rose-50 p-4 text-sm text-rose-700">
          Не удалось загрузить сессию. Проверьте backend.
        </div>
      )}

      {data && (
        <>
          <div className="rounded-xl border border-slate-200 bg-white p-6">
            <div className="mb-6 flex items-center justify-between">
              <div className="font-mono text-3xl font-bold tracking-wider text-slate-800">
                {data.plate_number ?? "—"}
              </div>
              <span
                className={`rounded px-3 py-1 text-sm font-medium ${
                  sessionStatusBadgeClass[data.status]
                }`}
              >
                {sessionStatusLabel[data.status]}
              </span>
            </div>

            <dl className="grid grid-cols-1 gap-x-8 gap-y-4 sm:grid-cols-2">
              <Row label="Время въезда" value={formatDateTime(data.entry_time)} />
              <Row
                label="Время выезда"
                value={data.exit_time ? formatDateTime(data.exit_time) : "— (на парковке)"}
              />
              <Row
                label="Время стоянки"
                value={formatDuration(sessionDurationSeconds(data))}
              />
              <Row label="Сумма" value={formatAmount(data.amount)} />
              <Row label="Камера въезда" value={data.entry_camera_name ?? "—"} />
              <Row label="Камера выезда" value={data.exit_camera_name ?? "—"} />
            </dl>
          </div>

          {/* Фото */}
          {(data.vehicle_photo_url || data.plate_photo_url) && (
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              {data.vehicle_photo_url && (
                <PhotoCard
                  label="Фото автомобиля"
                  url={data.vehicle_photo_url}
                  onOpen={setPhoto}
                />
              )}
              {data.plate_photo_url && (
                <PhotoCard
                  label="Фото номера"
                  url={data.plate_photo_url}
                  onOpen={setPhoto}
                />
              )}
            </div>
          )}
        </>
      )}

      {photo && <PhotoModal url={photo} onClose={() => setPhoto(null)} />}
    </div>
  );
}

function Row({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div>
      <dt className="text-xs uppercase text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-slate-800">{value}</dd>
    </div>
  );
}

function PhotoCard({
  label,
  url,
  onOpen,
}: {
  label: string;
  url: string;
  onOpen: (url: string) => void;
}) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="border-b border-slate-200 px-4 py-2 text-sm font-medium text-slate-600">
        {label}
      </div>
      <button onClick={() => onOpen(url)} className="block w-full">
        <img src={url} alt={label} className="max-h-80 w-full object-cover" />
      </button>
    </div>
  );
}
