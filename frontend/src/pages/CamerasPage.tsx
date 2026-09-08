import { useState } from "react";
import {
  useCameraStream,
  useCameras,
  useCheckCamera,
  useCreateCamera,
  useDeleteCamera,
  useGates,
  useUpdateCamera,
} from "../api/hooks";
import { StatTile } from "../components/StatTile";
import type { Camera, CameraInput } from "../api/types";
import { formatDateTime } from "../lib/format";

/** Пустая форма = «новая камера». id заполнен — режим редактирования. */
type FormState = CameraInput & { id?: number };

const EMPTY: FormState = {
  name: "",
  ip_address: "",
  type: "Hikvision",
  location: "",
  gate_id: null,
  direction: "entry",
  username: "admin",
  password: "",
  rtsp_port: 554,
  stream_path: "",
  stream_url: "",
};

export function CamerasPage() {
  const { data, isLoading, isError } = useCameras();
  const gates = useGates();
  const createCamera = useCreateCamera();
  const updateCamera = useUpdateCamera();
  const deleteCamera = useDeleteCamera();
  const checkCamera = useCheckCamera();
  const cameraStream = useCameraStream();

  const [form, setForm] = useState<FormState>(EMPTY);
  const [note, setNote] = useState<{ kind: "ok" | "err"; text: string } | null>(
    null,
  );

  const editing = form.id !== undefined;
  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const startEdit = (cam: Camera) => {
    setNote(null);
    setForm({
      id: cam.id,
      name: cam.name,
      ip_address: cam.ip_address ?? "",
      type: cam.type ?? "",
      location: cam.location ?? "",
      gate_id: cam.gate_id,
      direction: cam.direction,
      username: cam.username ?? "",
      // Пароль не приходит с бэкенда: пустое поле = «оставить прежний».
      password: "",
      rtsp_port: cam.rtsp_port,
      stream_path: cam.stream_path ?? "",
      stream_url: cam.stream_url ?? "",
    });
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.name?.trim()) return;
    const { id, ...rest } = form;
    // Пустые строки шлём как null, чтобы в БД не оседали «пустые» значения.
    const payload: CameraInput = Object.fromEntries(
      Object.entries(rest).map(([k, v]) => [k, v === "" ? null : v]),
    );
    const done = {
      onSuccess: () => {
        setForm(EMPTY);
        setNote({ kind: "ok", text: id ? "Камера обновлена" : "Камера добавлена" });
      },
      onError: (err: Error) => setNote({ kind: "err", text: err.message }),
    };
    if (id === undefined) createCamera.mutate(payload, done);
    else updateCamera.mutate({ id, patch: payload }, done);
  };

  const doCheck = (cam: Camera) => {
    setNote(null);
    checkCamera.mutate(cam.id, {
      onSuccess: (r) =>
        setNote({
          kind: r.reachable ? "ok" : "err",
          text: `${cam.name} · ${r.target}: ${r.detail ?? r.status}`,
        }),
      onError: (err: Error) => setNote({ kind: "err", text: err.message }),
    });
  };

  const doStream = (cam: Camera, action: "start" | "stop") => {
    setNote(null);
    cameraStream.mutate(
      { id: cam.id, action },
      {
        onSuccess: () =>
          setNote({
            kind: "ok",
            text:
              action === "start"
                ? `Поток «${cam.name}» запущен в CV — события пойдут в Сессии`
                : `Поток «${cam.name}» остановлен`,
          }),
        onError: (err: Error) => setNote({ kind: "err", text: err.message }),
      },
    );
  };

  const doDelete = (cam: Camera) => {
    if (!window.confirm(`Удалить камеру «${cam.name}» и все её события?`)) return;
    deleteCamera.mutate(cam.id, {
      onError: (err: Error) => setNote({ kind: "err", text: err.message }),
    });
  };

  const total = data?.length ?? 0;
  const online = data?.filter((c) => c.status === "online").length ?? 0;
  const offline = data?.filter((c) => c.status === "offline").length ?? 0;
  const busy =
    createCamera.isPending || updateCamera.isPending || cameraStream.isPending;

  return (
    <div className="space-y-6">
      <div>
        <div className="eyebrow">Инфраструктура КПП</div>
        <h2 className="font-display text-xl font-semibold text-ink">Камеры</h2>
        <p className="mt-1 text-sm text-ink-500/70">
          Реестр ANPR-устройств. Логин, пароль и порт нужны, чтобы забрать RTSP-поток:
          бэкенд собирает адрес сам и отдаёт его только CV-сервису — в браузер пароль
          не попадает.
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
          hint="ответили на проверку или прислали событие"
        />
        <StatTile eyebrow="Офлайн" value={offline} hint="нет связи с устройством" />
      </div>

      {/* Форма добавления / редактирования */}
      <form onSubmit={submit} className="card space-y-4 p-5">
        <div className="flex items-center justify-between">
          <div className="eyebrow">
            {editing ? `Редактирование · ${form.name}` : "Новая камера"}
          </div>
          {editing && (
            <button
              type="button"
              onClick={() => {
                setForm(EMPTY);
                setNote(null);
              }}
              className="text-xs text-ink-500/60 transition hover:text-ink"
            >
              отменить
            </button>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Название *" hint="им же назовётся поток в CV">
            <input
              value={form.name ?? ""}
              onChange={(e) => set("name", e.target.value)}
              placeholder="Entry-Cam-1"
              className="input w-full"
              required
            />
          </Field>
          <Field label="IP-адрес">
            <input
              value={form.ip_address ?? ""}
              onChange={(e) => set("ip_address", e.target.value)}
              placeholder="192.168.8.30"
              className="input w-full font-mono"
            />
          </Field>
          <Field label="Тип">
            <input
              value={form.type ?? ""}
              onChange={(e) => set("type", e.target.value)}
              placeholder="Hikvision ANPR"
              className="input w-full"
            />
          </Field>
          <Field label="Расположение">
            <input
              value={form.location ?? ""}
              onChange={(e) => set("location", e.target.value)}
              placeholder="Въезд со стороны трассы"
              className="input w-full"
            />
          </Field>
        </div>

        <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Логин камеры">
            <input
              value={form.username ?? ""}
              onChange={(e) => set("username", e.target.value)}
              placeholder="admin"
              className="input w-full font-mono"
              autoComplete="off"
            />
          </Field>
          <Field
            label="Пароль"
            hint={editing ? "пусто — оставить прежний" : "как в веб-морде камеры"}
          >
            <input
              type="password"
              value={form.password ?? ""}
              onChange={(e) => set("password", e.target.value)}
              placeholder="••••••"
              className="input w-full font-mono"
              autoComplete="new-password"
            />
          </Field>
          <Field label="Порт RTSP">
            <input
              type="number"
              min={1}
              max={65535}
              value={form.rtsp_port ?? 554}
              onChange={(e) => set("rtsp_port", Number(e.target.value))}
              className="input w-full font-mono"
            />
          </Field>
          <Field label="Путь потока" hint="пусто = субпоток 102">
            <input
              value={form.stream_path ?? ""}
              onChange={(e) => set("stream_path", e.target.value)}
              placeholder="/Streaming/Channels/102"
              className="input w-full font-mono"
            />
          </Field>
        </div>

        <div className="grid gap-4 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Направление" hint="в RTSP его больше взять неоткуда">
            <select
              value={form.direction ?? ""}
              onChange={(e) =>
                set(
                  "direction",
                  (e.target.value || null) as CameraInput["direction"],
                )
              }
              className="input w-full"
            >
              <option value="">— не задано —</option>
              <option value="entry">Въезд</option>
              <option value="exit">Выезд</option>
            </select>
          </Field>
          <Field label="Шлагбаум" hint="куда попадут её события">
            <select
              value={form.gate_id ?? ""}
              onChange={(e) =>
                set("gate_id", e.target.value ? Number(e.target.value) : null)
              }
              className="input w-full"
            >
              <option value="">— не привязана —</option>
              {gates.data?.map((g) => (
                <option key={g.id} value={g.id}>
                  {g.name}
                  {g.zone ? ` · ${g.zone}` : ""}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label="URL потока целиком"
            hint="для телефона/NVR — побеждает поля выше"
          >
            <input
              value={form.stream_url ?? ""}
              onChange={(e) => set("stream_url", e.target.value)}
              placeholder="http://100.64.0.2:4747/video"
              className="input w-full font-mono"
            />
          </Field>
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={busy}
            className="rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark disabled:opacity-50"
          >
            {busy ? "Сохранение…" : editing ? "Сохранить" : "Добавить камеру"}
          </button>
          {note && (
            <span
              className={`text-sm ${
                note.kind === "ok" ? "text-emerald-600" : "text-rose-500"
              }`}
            >
              {note.text}
            </span>
          )}
        </div>
      </form>

      {/* Таблица камер */}
      <div className="card overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="bg-paper text-xs uppercase tracking-wide text-ink-500/60">
            <tr>
              <th className="px-4 py-3">Название</th>
              <th className="px-4 py-3">Направление</th>
              <th className="px-4 py-3">Поток</th>
              <th className="px-4 py-3">Статус</th>
              <th className="px-4 py-3">Последний сигнал</th>
              <th className="px-4 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {isLoading && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-ink-500/50">
                  Загрузка…
                </td>
              </tr>
            )}
            {isError && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-rose-500">
                  Ошибка загрузки
                </td>
              </tr>
            )}
            {!isLoading && data?.length === 0 && (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-ink-500/50">
                  Камеры ещё не добавлены
                </td>
              </tr>
            )}
            {data?.map((cam) => (
              <tr key={cam.id} className="animate-fade-up hover:bg-paper">
                <td className="px-4 py-3">
                  <div className="font-medium text-ink">{cam.name}</div>
                  <div className="text-xs text-ink-500/60">
                    {cam.location || cam.type || "—"}
                  </div>
                </td>
                <td className="px-4 py-3">
                  {cam.direction ? (
                    <span
                      className={`rounded px-2 py-0.5 text-xs font-medium ${
                        cam.direction === "entry"
                          ? "bg-emerald-100 text-emerald-700"
                          : "bg-sky-100 text-sky-700"
                      }`}
                    >
                      {cam.direction === "entry" ? "Въезд" : "Выезд"}
                    </span>
                  ) : (
                    <span className="text-xs text-amber-600">не задано</span>
                  )}
                </td>
                <td className="px-4 py-3">
                  <div className="max-w-[22rem] truncate font-mono text-xs text-ink-500/70">
                    {cam.stream_url_display ?? "—"}
                  </div>
                  {cam.username && !cam.has_password && (
                    <div className="text-xs text-amber-600">пароль не задан</div>
                  )}
                </td>
                <td className="px-4 py-3">
                  <StatusBadge status={cam.status} />
                </td>
                <td className="px-4 py-3 font-mono text-xs text-ink-500/70">
                  {cam.last_seen_at ? formatDateTime(cam.last_seen_at) : "—"}
                </td>
                <td className="px-4 py-3">
                  <div className="flex flex-wrap justify-end gap-1.5">
                    <RowButton
                      onClick={() => doCheck(cam)}
                      disabled={checkCamera.isPending}
                    >
                      Проверить
                    </RowButton>
                    <RowButton onClick={() => doStream(cam, "start")} disabled={busy}>
                      ▶ В CV
                    </RowButton>
                    <RowButton onClick={() => doStream(cam, "stop")} disabled={busy}>
                      ■ Стоп
                    </RowButton>
                    <RowButton onClick={() => startEdit(cam)}>Изменить</RowButton>
                    <RowButton onClick={() => doDelete(cam)} danger>
                      Удалить
                    </RowButton>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function RowButton({
  children,
  onClick,
  disabled,
  danger,
}: {
  children: React.ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg border px-2.5 py-1 text-xs font-medium transition disabled:opacity-40 ${
        danger
          ? "border-line text-ink-500/70 hover:border-rose-300 hover:text-rose-600"
          : "border-line text-ink-600 hover:border-sky"
      }`}
    >
      {children}
    </button>
  );
}

function StatusBadge({ status }: { status: string }) {
  const cls =
    status === "online"
      ? "bg-emerald-100 text-emerald-700"
      : status === "offline"
        ? "bg-rose-100 text-rose-700"
        : "bg-slate-100 text-slate-500";
  const label =
    status === "online"
      ? "онлайн"
      : status === "offline"
        ? "офлайн"
        : "не проверялась";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded px-2 py-0.5 text-xs font-medium ${cls}`}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {label}
    </span>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-xs font-medium text-ink-500/70">
        {label}
        {hint && <span className="ml-1 font-normal text-ink-500/45">· {hint}</span>}
      </span>
      {children}
    </label>
  );
}
