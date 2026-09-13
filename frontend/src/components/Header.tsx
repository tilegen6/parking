import { useQueryClient } from "@tanstack/react-query";
import { useDashboardStats } from "../api/hooks";

export function Header() {
  const qc = useQueryClient();
  const { data, isError, isFetching } = useDashboardStats();

  // Статус backend определяем по успешности запроса статистики
  const backendOnline = !isError && data !== undefined;
  const camerasOnline = data?.cameras_online ?? 0;
  const camerasTotal = data?.cameras_total ?? 0;

  return (
    <header className="flex h-16 items-center justify-between border-b border-slate-200 bg-white px-6">
      <h1 className="text-base font-semibold text-slate-700">
        Система распознавания номеров
      </h1>

      <div className="flex items-center gap-4">
        <StatusDot
          ok={backendOnline}
          label={backendOnline ? "Backend online" : "Backend offline"}
        />
        <StatusDot
          ok={camerasOnline > 0}
          label={`Камеры ${camerasOnline}/${camerasTotal}`}
        />
        <button
          onClick={() => qc.invalidateQueries()}
          className="rounded-lg border border-slate-200 px-3 py-1.5 text-sm font-medium text-slate-600 transition hover:bg-slate-50"
        >
          {isFetching ? "Обновление…" : "↻ Обновить"}
        </button>
      </div>
    </header>
  );
}

function StatusDot({ ok, label }: { ok: boolean; label: string }) {
  return (
    <div className="flex items-center gap-2 text-sm text-slate-600">
      <span
        className={`inline-block h-2.5 w-2.5 rounded-full ${
          ok ? "bg-emerald-500" : "bg-rose-500"
        }`}
      />
      {label}
    </div>
  );
}
