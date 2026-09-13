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
    <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <div className="mb-2 flex items-center gap-2 text-sm font-medium text-slate-500">
        <span>{icon}</span>
        {title}
      </div>
      <div className="text-slate-800">{children}</div>
    </div>
  );
}
