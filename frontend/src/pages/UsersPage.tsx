import { useState } from "react";
import type { AuthUser, UserRole } from "../api/auth";
import { useAuditLog, useCreateUser, useUpdateUser, useUsers } from "../api/hooks";
import { StatTile } from "../components/StatTile";
import { useAuth } from "../context/AuthContext";
import { formatDateTime } from "../lib/format";

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Администратор",
  operator: "Оператор",
  list_manager: "Ведение списков",
};

const ROLE_BADGE: Record<UserRole, string> = {
  admin: "bg-rose-100 text-rose-700",
  operator: "bg-sky-100 text-sky-700",
  list_manager: "bg-amber-100 text-amber-700",
};

export function UsersPage() {
  const { user: me } = useAuth();
  const { data, isLoading } = useUsers();
  const audit = useAuditLog();
  const createUser = useCreateUser();
  const updateUser = useUpdateUser();

  const [form, setForm] = useState({
    username: "",
    password: "",
    full_name: "",
    role: "operator" as UserRole,
  });
  const [err, setErr] = useState<string | null>(null);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    setErr(null);
    createUser.mutate(
      {
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name.trim() || null,
        role: form.role,
      },
      {
        onSuccess: () =>
          setForm({ username: "", password: "", full_name: "", role: "operator" }),
        onError: (e2) =>
          setErr(e2 instanceof Error ? e2.message : "Ошибка создания"),
      },
    );
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Доступ</div>
        <h2 className="font-display text-xl font-semibold text-ink">Пользователи</h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Учётки диспетчерской и их роли. Все действия со списками и сессиями
          фиксируются с привязкой к личности — журнал ниже.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          eyebrow="Всего учёток"
          value={isLoading ? "…" : (data?.length ?? 0)}
          hint="в системе"
        />
        <StatTile
          eyebrow="Активных"
          value={isLoading ? "…" : (data?.filter((u) => u.is_active).length ?? 0)}
          hint="могут входить"
        />
        <StatTile
          eyebrow="Админов"
          value={
            isLoading ? "…" : (data?.filter((u) => u.role === "admin").length ?? 0)
          }
          hint="полный доступ"
        />
      </div>

      {/* Создание */}
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="eyebrow">Новый пользователь</div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Логин *">
            <input
              value={form.username}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
              className="input w-full"
              placeholder="operator1"
              required
            />
          </Field>
          <Field label="Пароль *">
            <input
              type="password"
              value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              className="input w-full"
              placeholder="мин. 4 символа"
              required
            />
          </Field>
          <Field label="Имя">
            <input
              value={form.full_name}
              onChange={(e) => setForm({ ...form, full_name: e.target.value })}
              className="input w-full"
              placeholder="Иван Иванов"
            />
          </Field>
          <Field label="Роль">
            <select
              value={form.role}
              onChange={(e) =>
                setForm({ ...form, role: e.target.value as UserRole })
              }
              className="input w-full"
            >
              <option value="operator">Оператор</option>
              <option value="list_manager">Ведение списков</option>
              <option value="admin">Администратор</option>
            </select>
          </Field>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={createUser.isPending || !form.username.trim() || !form.password}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {createUser.isPending ? "Создание…" : "Создать пользователя"}
          </button>
          {err && <span className="text-sm text-rose-500">{err}</span>}
        </div>
      </form>

      {/* Таблица пользователей */}
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">Логин</th>
              <th className="px-4 py-3">Имя</th>
              <th className="px-4 py-3">Роль</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3 text-right">Действия</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {data?.map((u) => (
              <UserRow
                key={u.id}
                u={u}
                isMe={u.id === me?.id}
                onRole={(role) => updateUser.mutate({ id: u.id, patch: { role } })}
                onToggle={() =>
                  updateUser.mutate({ id: u.id, patch: { is_active: !u.is_active } })
                }
                busy={updateUser.isPending}
              />
            ))}
          </tbody>
        </table>
      </div>

      {/* Журнал аудита */}
      <div className="card overflow-hidden">
        <div className="border-b border-line px-5 py-3">
          <div className="eyebrow">Журнал действий</div>
          <p className="mt-0.5 text-xs text-ink-500/60">
            кто / что / когда — привязка к личности
          </p>
        </div>
        <ul className="max-h-80 divide-y divide-line overflow-y-auto">
          {audit.data?.length === 0 && (
            <li className="px-5 py-8 text-center text-sm text-ink-500/50">
              Действий пока нет
            </li>
          )}
          {audit.data?.map((a) => (
            <li key={a.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
              <span className="w-36 font-mono text-[11px] text-ink-500/50">
                {formatDateTime(a.created_at)}
              </span>
              <span className="font-medium text-ink">{a.username ?? "—"}</span>
              <span className="rounded bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-600">
                {a.action}
              </span>
              <span className="text-ink-500/60">{a.detail ?? ""}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function UserRow({
  u,
  isMe,
  onRole,
  onToggle,
  busy,
}: {
  u: AuthUser;
  isMe: boolean;
  onRole: (role: UserRole) => void;
  onToggle: () => void;
  busy: boolean;
}) {
  return (
    <tr className="animate-fade-up hover:bg-paper">
      <td className="px-4 py-3 font-medium text-ink">
        {u.username}
        {isMe && <span className="ml-1.5 text-xs text-ink-500/50">(вы)</span>}
      </td>
      <td className="px-4 py-3 text-ink-500/70">{u.full_name ?? "—"}</td>
      <td className="px-4 py-3">
        <select
          value={u.role}
          disabled={isMe || busy}
          onChange={(e) => onRole(e.target.value as UserRole)}
          className={`rounded px-2 py-0.5 text-xs font-medium ${ROLE_BADGE[u.role]} disabled:opacity-70`}
        >
          <option value="admin">{ROLE_LABEL.admin}</option>
          <option value="operator">{ROLE_LABEL.operator}</option>
          <option value="list_manager">{ROLE_LABEL.list_manager}</option>
        </select>
      </td>
      <td className="px-4 py-3">
        <span
          className={`rounded px-2 py-0.5 text-xs font-medium ${
            u.is_active ? "bg-emerald-100 text-emerald-700" : "bg-slate-100 text-slate-500"
          }`}
        >
          {u.is_active ? "активен" : "отключён"}
        </span>
      </td>
      <td className="px-4 py-3 text-right">
        <button
          onClick={onToggle}
          disabled={isMe || busy}
          className="rounded-md border border-line px-2.5 py-1 text-xs font-medium text-ink-500/80 transition hover:border-sky disabled:opacity-40"
          title={isMe ? "Нельзя менять свою учётку" : ""}
        >
          {u.is_active ? "отключить" : "включить"}
        </button>
      </td>
    </tr>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-500/70">{label}</span>
      {children}
    </label>
  );
}
