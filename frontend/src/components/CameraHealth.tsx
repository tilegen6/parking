import type { Camera } from "../api/types";

export function CameraHealth({
  cameras,
  isLoading,
}: {
  cameras: Camera[];
  isLoading?: boolean;
}) {
  const online = cameras.filter((c) => c.status === "online").length;
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div>
          <div className="eyebrow">Оборудование</div>
          <h3 className="font-display text-sm font-semibold text-ink">Камеры</h3>
        </div>
        <span className="font-mono text-xs text-ink-500/60">
          {online}/{cameras.length} онлайн
        </span>
      </div>
      <ul className="divide-y divide-line">
        {isLoading && cameras.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-ink-500/50">Загрузка…</li>
        )}
        {!isLoading && cameras.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-ink-500/50">
            Камеры не добавлены
          </li>
        )}
        {cameras.map((c) => (
          <li key={c.id} className="flex items-center gap-3 px-5 py-3">
            <StatusDot status={c.status} />
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-ink">{c.name}</div>
              <div className="truncate text-xs text-ink-500/50">
                {c.location ?? c.ip_address ?? "—"}
              </div>
            </div>
            <span className="ml-auto font-mono text-[11px] uppercase tracking-wide text-ink-500/50">
              {c.status}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function StatusDot({ status }: { status: string }) {
  const color =
    status === "online"
      ? "bg-emerald-500"
      : status === "offline"
        ? "bg-rose-500"
        : "bg-slate-300";
  return <span className={`h-2.5 w-2.5 flex-shrink-0 rounded-full ${color}`} />;
}
