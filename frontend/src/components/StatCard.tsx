import type { ReactNode } from "react";

export function StatCard({
  title,
  icon,
  children,
}: {
  title: string;
  icon: string;
  children: ReactNode;
}) {
  return (
    <div className="card p-5">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-ink-500/70">
        <span>{icon}</span>
        {title}
      </div>
      <div className="text-ink">{children}</div>
    </div>
  );
}
