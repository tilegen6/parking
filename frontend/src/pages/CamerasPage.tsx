import { useState } from "react";
import { useCameras, useCreateCamera } from "../api/hooks";
import { StatTile } from "../components/StatTile";
import { formatDateTime } from "../lib/format";

export function CamerasPage() {
  const { data, isLoading, isError } = useCameras();
  const createCamera = useCreateCamera();

  const [form, setForm] = useState({
    name: "",
    ip_address: "",
    type: "",
    location: "",
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name.trim()) return;
    createCamera.mutate(
      {
        name: form.name,
        ip_address: form.ip_address || null,
        type: form.type || null,
        location: form.location || null,
      },
      {
        onSuccess: () =>
          setForm({ name: "", ip_address: "", type: "", location: "" }),
      },
    );
  };

  const total = data?.length ?? 0;
  const online = data?.filter((c) => c.status === "online").length ?? 0;
  const offline = data?.filter((c) => c.status === "offline").length ?? 0;

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Инфраструктура КПП</div>
        <h2 className="font-display text-xl font-semibold text-ink">Камеры</h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Реестр ANPR-устройств на въездах и выездах. Добавляй камеры и следи за их
          состоянием в сети.
        </p>
      </div>

      {/* KPI */}
      <div className="grid gap-4 sm:grid-cols-3">
        <StatTile
          eyebrow="Всего камер"
          value={isLoading ? "…" : total}
          hint="устройств в реестре"
        />
        <StatTile
          eyebrow="Онлайн"
          value={online}
          unit={`/ ${total}`}
          hint="устройств в сети"
        />
        <StatTile
          eyebrow="Офлайн"
          value={offline}
          hint="нет связи с устройством"
        />
      </div>

      {/* Форма добавления */}
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="eyebrow">Новая камера</div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Название *">
            <input
              value={form.name}
              onChange={(e) => setForm({ ...form, name: e.target.value })}
              placeholder="Entry-Cam-1"
              className="input w-full"
              required
            />
          </Field>
          <Field label="IP-адрес">
            <input
              value={form.ip_address}
              onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
              placeholder="192.168.1.64"
              className="input w-full font-mono"
            />
          </Field>
          <Field label="Тип">
            <input
              value={form.type}
              onChange={(e) => setForm({ ...form, type: e.target.value })}
              placeholder="Hikvision ANPR"
              className="input w-full"
            />
          </Field>
          <Field label="Расположение">
            <input
              value={form.location}
              onChange={(e) => setForm({ ...form, location: e.target.value })}
              placeholder="Въезд"
              className="input w-full"
            />
          </Field>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={createCamera.isPending}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {createCamera.isPending ? "Добавление…" : "Добавить камеру"}
          </button>
          {createCamera.isError && (
            <span className="text-sm text-rose-500">Ошибка добавления</span>
          )}
        </div>
      </form>

      {/* Таблица камер */}
      <div className="card overflow-hidden">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">ID</th>
              <th className="px-4 py-3">Название</th>
              <th className="px-4 py-3">IP</th>
              <th className="px-4 py-3">Тип</th>
              <th className="px-4 py-3">Расположение</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3">Добавлена</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-ink-500/50">
                  Загрузка…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-rose-500">
                  Ошибка загрузки
                </td>
              </tr>
            )}
            {!isLoading && data?.length === 0 && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-ink-500/50">
                  Камеры ещё не добавлены
                </td>
              </tr>
            )}
            {data?.map((cam) => (
              <tr key={cam.id} className="animate-fade-up hover:bg-paper">
                <td className="px-4 py-3 font-mono text-ink-500/70">{cam.id}</td>
                <td className="px-4 py-3 font-medium text-ink">{cam.name}</td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {cam.ip_address ?? "—"}
                </td>
                <td className="px-4 py-3 text-ink-500/70">{cam.type ?? "—"}</td>
                <td className="px-4 py-3 text-ink-500/70">{cam.location ?? "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={cam.status} />
                </td>
                <td className="px-4 py-3 font-mono text-ink-500/70">
                  {formatDateTime(cam.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "online"
      ? "bg-emerald-100 text-emerald-700"
      : status === "offline"
        ? "bg-rose-100 text-rose-700"
        : "bg-slate-100 text-slate-500";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {status}
    </span>
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
