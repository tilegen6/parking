import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Дашборд", icon: "📊", end: true },
  { to: "/events", label: "События", icon: "🚗" },
  { to: "/cameras", label: "Камеры", icon: "📷" },
];

export function Sidebar() {
  return (
    <aside className="flex w-60 flex-shrink-0 flex-col bg-slate-900 text-slate-100">
      <div className="flex h-16 items-center gap-2 px-6 text-lg font-semibold">
        <span className="text-brand">🅿️</span>
        Smart Parking
      </div>
      <nav className="flex-1 space-y-1 px-3 py-4">
        {links.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                isActive
                  ? "bg-brand text-white"
                  : "text-slate-300 hover:bg-slate-800 hover:text-white"
              }`
            }
          >
            <span>{link.icon}</span>
            {link.label}
          </NavLink>
        ))}
      </nav>
      <div className="px-6 py-4 text-xs text-slate-500">v0.1.0 · MVP</div>
    </aside>
  );
}
