import { NavLink } from "react-router-dom";

const links = [
  { to: "/", label: "Дашборд", icon: "▦", end: true },
  { to: "/events", label: "События", icon: "◎" },
  { to: "/sessions", label: "Сессии", icon: "▤" },
  { to: "/active", label: "На парковке", icon: "▣" },
  { to: "/cameras", label: "Камеры", icon: "▷" },
  { to: "/recognize", label: "Тест CV", icon: "✦" },
  { to: "/simulator", label: "Симулятор", icon: "⚡" },
];

function NavContent({ onNavigate }: { onNavigate?: () => void }) {
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
        {links.map((link) => (
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
