import { useState } from "react";
import { useAuth } from "../context/AuthContext";

export function LoginPage() {
  const { login } = useAuth();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(username.trim(), password);
    } catch (err) {
      setError(
        err instanceof Error ? err.message : "Не удалось войти. Проверьте данные.",
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-ink p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-5 rounded-2xl bg-surface p-8 shadow-2xl"
      >
        <div className="flex items-center gap-3">
          <span className="inline-flex items-stretch overflow-hidden rounded ring-1 ring-line">
            <span className="bg-ink px-1.5 py-1 font-mono text-[11px] font-extrabold leading-none text-white">
              02
            </span>
            <span className="flex items-center bg-sky px-1 font-mono text-[7px] font-bold leading-none text-white">
              KZ
            </span>
          </span>
          <div className="leading-tight">
            <div className="font-display text-base font-semibold text-ink">
              Smart Parking
            </div>
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-sky-600">
              ANPR · диспетчерская
            </div>
          </div>
        </div>

        <div>
          <div className="eyebrow">Вход в систему</div>
          <h1 className="font-display text-xl font-semibold text-ink">
            Авторизация
          </h1>
        </div>

        <label className="block">
          <span className="mb-1 block text-xs font-medium text-ink-500/70">
            Логин
          </span>
          <input
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            autoFocus
            className="input w-full"
            placeholder="admin"
            required
          />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-ink-500/70">
            Пароль
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="input w-full"
            placeholder="••••••"
            required
          />
        </label>

        {error && (
          <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-600">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={busy || !username.trim() || !password}
          className="w-full rounded-lg bg-brand px-4 py-2.5 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-50"
        >
          {busy ? "Вход…" : "Войти"}
        </button>
      </form>
    </div>
  );
}
