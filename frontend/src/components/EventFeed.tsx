import type { RecognitionEvent } from "../api/types";
import {
  directionBadgeClass,
  directionLabel,
  formatConfidence,
  timeAgo,
} from "../lib/format";
import { PlateReadout } from "./PlateReadout";

export function EventFeed({
  events,
  isLoading,
}: {
  events: RecognitionEvent[];
  isLoading?: boolean;
}) {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center justify-between border-b border-line px-5 py-3.5">
        <div>
          <div className="eyebrow">Поток распознаваний</div>
          <h3 className="font-display text-sm font-semibold text-ink">
            Последние события
          </h3>
        </div>
        <LiveTag />
      </div>
      <ul className="divide-y divide-line">
        {isLoading && events.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-ink-500/50">Загрузка…</li>
        )}
        {!isLoading && events.length === 0 && (
          <li className="px-5 py-10 text-center text-sm text-ink-500/50">
            Событий пока нет
          </li>
        )}
        {events.map((e) => (
          <li
            key={e.id}
            className="flex animate-fade-up items-center gap-4 px-5 py-3"
          >
            <PlateReadout plate={e.plate_number} size="sm" />
            <span
              className={`rounded px-2 py-0.5 text-xs font-medium ${directionBadgeClass[e.direction]}`}
            >
              {directionLabel[e.direction]}
            </span>
            <span className="hidden truncate text-sm text-ink-500/70 sm:block">
              {e.camera_name ?? "—"}
            </span>
            <span className="ml-auto font-mono text-xs text-ink-500/60">
              {formatConfidence(e.confidence)}
            </span>
            <span className="w-24 text-right text-xs text-ink-500/50">
              {timeAgo(e.event_time)}
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function LiveTag() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-50 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-emerald-700">
      <span className="relative flex h-1.5 w-1.5">
        <span className="absolute inline-flex h-full w-full animate-pulse-ring rounded-full bg-emerald-400" />
        <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-emerald-500" />
      </span>
      live
    </span>
  );
}
