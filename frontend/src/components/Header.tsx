import { useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useAlerts, useDashboardStats } from "../api/hooks";
import { useAuth } from "../context/AuthContext";

const ROLE_SHORT: Record<string, string> = {
  admin: "админ",
  operator: "оператор",
  list_manager: "списки",
};

export function Header({ onMenu }: { onMenu?: () => void }) {
  const qc = useQueryClient();
  const { data, isError, isFetching } = useDashboardStats();
  const { user, logout } = useAuth();
  const canManageLists = user?.role === "admin" || user?.role === "list_manager";
  const alerts = useAlerts();
  const newAlerts = canManageLists ? (alerts.data?.length ?? 0) : 0;

  const backendOnline = !isError && data !== undefined;
  const camerasOnline = data?.cameras_online ?? 0;
  const camerasTotal = data?.cameras_total ?? 0;

  return (
    <header className="flex h-16 items-center justify-between border-b border-line bg-surface/80 px-4 backdrop-blur sm:px-6">
      <div className="flex items-center gap-3">
        <button
          onClick={onMenu}
          aria-label="Открыть меню"
          className="rounded-lg border border-line px-2.5 py-1.5 text-ink-600 transition hover:border-sky lg:hidden"
        >
          ☰
        </button>
        <div>
          <div className="eyebrow">Контроль КПП</div>
          <h1 className="font-display text-base font-semibold text-ink">
            Распознавание номеров
          </h1>
        </div>
      </div>

      <div className="flex items-center gap-2.5">
        {newAlerts > 0 && (
          <Link
            to="/access-lists"
            className="inline-flex animate-pulse items-center gap-1.5 rounded-full bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-rose-700"
            title="Машины из красного списка — требуется реакция"
          >
            🚨 {newAlerts}
          </Link>
        )}
        <span className="hidden sm:contents">
          <Pill ok={backendOnline} label={backendOnline ? "Backend" : "Backend offline"} />
          <Pill ok={camerasOnline > 0} label={`Камеры ${camerasOnline}/${camerasTotal}`} />
        </span>
        <button
          onClick={() => qc.invalidateQueries()}
          className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink-600 transition hover:border-sky hover:text-sky-700"
        >
          {isFetching ? "Обновление…" : "↻ Обновить"}
        </button>
        {user && (
          <div className="flex items-center gap-2 border-l border-line pl-2.5">
            <div className="hidden text-right leading-tight sm:block">
              <div className="text-sm font-medium text-ink">{user.username}</div>
              <div className="font-mono text-[10px] uppercase tracking-wider text-ink-500/50">
                {ROLE_SHORT[user.role] ?? user.role}
              </div>
            </div>
            <button
              onClick={logout}
              title="Выйти"
              className="rounded-lg border border-line px-3 py-1.5 text-sm font-medium text-ink-600 transition hover:border-rose-300 hover:text-rose-600"
            >
              Выйти
            </button>
          </div>
        )}
      </div>
    </header>
  );
}

function Pill({ ok, label }: { ok: boolean; label: string }) {
  return (
    <span className="inline-flex items-center gap-2 rounded-full border border-line bg-paper px-3 py-1.5 text-xs font-medium text-ink-600">
      <span className="relative flex h-2 w-2">
        {ok && (
          <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-emerald-400" />
        )}
        <span
          className={`relative inline-flex h-2 w-2 rounded-full ${
            ok ? "bg-emerald-500" : "bg-rose-500"
          }`}
        />
      </span>
      {label}
    </span>
  );
}
