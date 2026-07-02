import { useState } from "react";
import { useCameras, useCreateCamera } from "../api/hooks";
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

  return (
    <div className="space-y-6">
      <h2 className="text-xl font-semibold text-slate-800">Камеры</h2>

      {/* Форма добавления */}
      <form
        onSubmit={submit}
        className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 bg-white p-4"
      >
        <Field label="Название *">
          <input
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
            placeholder="Entry-Cam-1"
            className="input"
            required
          />
        </Field>
        <Field label="IP-адрес">
          <input
            value={form.ip_address}
            onChange={(e) => setForm({ ...form, ip_address: e.target.value })}
            placeholder="192.168.1.64"
            className="input"
          />
        </Field>
        <Field label="Тип">
          <input
            value={form.type}
            onChange={(e) => setForm({ ...form, type: e.target.value })}
            placeholder="Hikvision ANPR"
            className="input"
          />
        </Field>
        <Field label="Расположение">
          <input
            value={form.location}
            onChange={(e) => setForm({ ...form, location: e.target.value })}
            placeholder="Въезд"
            className="input"
          />
        </Field>
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
      </form>

      {/* Таблица камер */}
      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-left text-sm">
          <thead className="bg-slate-50 text-xs uppercase text-slate-500">
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
          <tbody className="divide-y divide-slate-100">
            {isLoading && (
              <tr>
                <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
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
                <td colSpan={7} className="px-4 py-12 text-center text-slate-400">
                  Камеры ещё не добавлены
                </td>
              </tr>
            )}
            {data?.map((cam) => (
              <tr key={cam.id} className="hover:bg-slate-50">
                <td className="px-4 py-3 text-slate-500">{cam.id}</td>
                <td className="px-4 py-3 font-medium">{cam.name}</td>
                <td className="px-4 py-3 text-slate-600">{cam.ip_address ?? "—"}</td>
                <td className="px-4 py-3 text-slate-600">{cam.type ?? "—"}</td>
                <td className="px-4 py-3 text-slate-600">{cam.location ?? "—"}</td>
                <td className="px-4 py-3">
                  <StatusBadge status={cam.status} />
                </td>
                <td className="px-4 py-3 text-slate-500">
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
    <span className={`rounded px-2 py-0.5 text-xs font-medium ${cls}`}>{status}</span>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      {children}
    </label>
  );
}
