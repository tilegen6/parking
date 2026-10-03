import { Link } from "react-router-dom";

export function PaySuccessPage() {
  return (
    <div className="mx-auto max-w-md">
      <div className="card space-y-4 p-8 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-emerald-100 text-3xl text-emerald-600">
          ✓
        </div>
        <h2 className="font-display text-xl font-semibold text-ink">Оплачено</h2>
        <p className="text-sm text-ink-500/70">
          Парковка оплачена — выезд разрешён.
        </p>
        <Link
          to="/sessions"
          className="inline-block rounded-lg bg-brand px-4 py-2 text-sm font-medium text-white transition hover:bg-brand-dark"
        >
          К сессиям
        </Link>
      </div>
    </div>
  );
}

export function PayErrorPage() {
  return (
    <div className="mx-auto max-w-md">
      <div className="card space-y-4 p-8 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-full bg-rose-100 text-3xl text-rose-600">
          ✕
        </div>
        <h2 className="font-display text-xl font-semibold text-ink">
          Оплата не прошла
        </h2>
        <p className="text-sm text-ink-500/70">
          Что-то пошло не так. Попробуйте ещё раз или проверьте, запущен ли backend.
        </p>
        <Link
          to="/sessions"
          className="inline-block rounded-lg border border-line px-4 py-2 text-sm font-medium text-ink-600 transition hover:border-sky"
        >
          К сессиям
        </Link>
      </div>
    </div>
  );
}
