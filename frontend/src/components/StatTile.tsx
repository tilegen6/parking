import type { ReactNode } from "react";

export function StatTile({
  eyebrow,
  value,
  unit,
  hint,
}: {
  eyebrow: string;
  value: ReactNode;
  unit?: string;
  hint?: ReactNode;
}) {
  return (
    <div className="card p-5 transition hover:shadow-hero">
      <div className="eyebrow">{eyebrow}</div>
      <div className="mt-2 flex items-baseline gap-1.5">
        <span className="font-display text-4xl font-bold leading-none text-ink">
          {value}
        </span>
        {unit && <span className="text-sm font-medium text-ink-500/60">{unit}</span>}
      </div>
      {hint && <div className="mt-2 text-xs text-ink-500/70">{hint}</div>}
    </div>
  );
}
