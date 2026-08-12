import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

type NavItem = { to: string; label: string; icon: string; end?: boolean };

const links: NavItem[] = [
  { to: "/", label: "Дашборд", icon: "▦", end: true },
  { to: "/events", label: "События", icon: "◎" },
  { to: "/sessions", label: "Сессии", icon: "▤" },
  { to: "/active", label: "На парковке", icon: "▣" },
  { to: "/tariffs", label: "Тарифы", icon: "₸" },
  { to: "/gates", label: "Шлагбаумы", icon: "⊟" },
  { to: "/cameras", label: "Камеры", icon: "▷" },
  { to: "/studio", label: "Студия", icon: "⚙" },
];

// Ведение списков — list_manager и admin
const managerLinks: NavItem[] = [
  { to: "/access-lists", label: "Списки", icon: "◑" },
];
// Пункты только для администратора
const adminLinks: NavItem[] = [{ to: "/users", label: "Пользователи", icon: "◍" }];

function NavContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  const role = user?.role;
  const items: NavItem[] = [
    ...links,
    ...(role === "admin" || role === "list_manager" ? managerLinks : []),
    ...(role === "admin" ? adminLinks : []),
  ];
  return (
    <>
      <div className="flex h-16 items-center gap-3 border-b border-white/5 px-5">
        <span className="inline-flex items-stretch overflow-hidden rounded ring-1 ring-white/25">
          <span className="bg-white px-1.5 py-1 font-mono text-[11px] font-extrabold leading-none text-ink">
            02
          </span>
          <span className="flex items-center bg-sky px-1 font-mono text-[7px] font-bold leading-none text-white">
            KZ
          </span>
        </span>
        <div className="leading-tight">
          <div className="font-display text-sm font-semibold text-white">
            Smart Parking
          </div>
          <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-sky-400">
            ANPR · диспетчерская
          </div>
        </div>
      </div>

      <nav className="flex-1 space-y-1 px-3 py-5">
        {items.map((link) => (
          <NavLink
            key={link.to}
            to={link.to}
            end={link.end}
            onClick={onNavigate}
            className={({ isActive }) =>
              `flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition ${
                isActive
                  ? "bg-sky text-white shadow-[0_10px_22px_-12px_rgba(0,166,200,0.9)]"
                  : "text-slate-400 hover:bg-white/5 hover:text-white"
              }`
            }
          >
            <span className="w-4 text-center text-base leading-none">{link.icon}</span>
            {link.label}
          </NavLink>
        ))}
      </nav>

      <div className="border-t border-white/5 px-5 py-4 font-mono text-[10px] uppercase tracking-wider text-slate-500">
        v0.1.0 · MVP
      </div>
    </>
  );
}

export function Sidebar({
  open = false,
  onClose,
}: {
  open?: boolean;
  onClose?: () => void;
}) {
  return (
    <>
      {/* Десктоп: постоянная панель */}
      <aside className="hidden w-64 flex-shrink-0 flex-col bg-ink text-slate-300 lg:flex">
        <NavContent />
      </aside>

      {/* Мобайл: выезжающий drawer */}
      {open && (
        <div className="fixed inset-0 z-40 lg:hidden">
          <div
            className="absolute inset-0 bg-ink/60 backdrop-blur-sm"
            onClick={onClose}
            aria-hidden
          />
          <aside className="absolute inset-y-0 left-0 flex w-64 flex-col bg-ink text-slate-300 shadow-2xl">
            <NavContent onNavigate={onClose} />
          </aside>
        </div>
      )}
    </>
  );
}
