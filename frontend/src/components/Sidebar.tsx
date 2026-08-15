import { NavLink } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

type Role = "admin" | "operator" | "list_manager";
type NavItem = {
  to: string;
  label: string;
  icon: string;
  end?: boolean;
  /** Кому показывать. Не задано — всем авторизованным. */
  roles?: Role[];
};
type NavGroup = { title: string; items: NavItem[] };

// Порядок групп = порядок рабочего дня: сначала «что происходит сейчас»,
// потом справочники, потом администрирование. Тестовый стенд — отдельно внизу.
const groups: NavGroup[] = [
  {
    title: "Оперативка",
    items: [
      { to: "/", label: "Дашборд", icon: "▦", end: true },
      { to: "/active", label: "На парковке", icon: "▣" },
      { to: "/sessions", label: "Сессии", icon: "▤" },
      { to: "/events", label: "События", icon: "◎" },
    ],
  },
  {
    title: "Оборудование",
    items: [
      { to: "/gates", label: "Шлагбаумы", icon: "⊟" },
      { to: "/cameras", label: "Камеры", icon: "▷" },
    ],
  },
  {
    title: "Правила доступа",
    items: [
      {
        to: "/access-lists",
        label: "Списки",
        icon: "◑",
        roles: ["admin", "list_manager"],
      },
      { to: "/tariffs", label: "Тарифы", icon: "₸" },
    ],
  },
  {
    title: "Администрирование",
    items: [
      { to: "/users", label: "Пользователи", icon: "◍", roles: ["admin"] },
    ],
  },
];

// Тестовый стенд: эмулирует проезды и создаёт сессии — только админу и
// визуально отделён от боевых разделов, чтобы не путать с рабочим экраном.
const studioLink: NavItem = {
  to: "/studio",
  label: "Студия (тест)",
  icon: "⚙",
  roles: ["admin"],
};

function visible(items: NavItem[], role?: string): NavItem[] {
  return items.filter((i) => !i.roles || (role && i.roles.includes(role as Role)));
}

function NavContent({ onNavigate }: { onNavigate?: () => void }) {
  const { user } = useAuth();
  const role = user?.role;
  const shownGroups = groups
    .map((g) => ({ ...g, items: visible(g.items, role) }))
    .filter((g) => g.items.length > 0);
  const showStudio = visible([studioLink], role).length > 0;
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

      <nav className="flex-1 overflow-y-auto px-3 py-4">
        {shownGroups.map((group) => (
          <div key={group.title} className="mb-4">
            <div className="px-3 pb-1.5 font-mono text-[10px] uppercase tracking-[0.16em] text-slate-500">
              {group.title}
            </div>
            <div className="space-y-1">
              {group.items.map((link) => (
                <NavItemLink key={link.to} link={link} onNavigate={onNavigate} />
              ))}
            </div>
          </div>
        ))}
      </nav>

      {showStudio && (
        <div className="border-t border-white/5 px-3 py-3">
          <NavItemLink link={studioLink} onNavigate={onNavigate} />
        </div>
      )}

      <div className="border-t border-white/5 px-5 py-4 font-mono text-[10px] uppercase tracking-wider text-slate-500">
        v0.1.0 · MVP
      </div>
    </>
  );
}

function NavItemLink({
  link,
  onNavigate,
}: {
  link: NavItem;
  onNavigate?: () => void;
}) {
  return (
    <NavLink
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
