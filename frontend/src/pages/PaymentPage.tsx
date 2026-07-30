import { useNavigate, useParams } from "react-router-dom";
import {
  useConfirmPaymentMock,
  useCreatePayment,
  useSession,
  useTariffs,
} from "../api/hooks";
import { PlateReadout } from "../components/PlateReadout";
import { amountDue, formatMoney } from "../lib/tariff";

export function PaymentPage() {
  const { sessionId } = useParams();
  const id = Number(sessionId);
  const navigate = useNavigate();
  const session = useSession(id);
  const tariffs = useTariffs();
  const createPayment = useCreatePayment();
  const confirm = useConfirmPaymentMock();
  const paying = createPayment.isPending || confirm.isPending;

  // Оплата (mock): создать платёж -> подтвердить webhook -> success/error
  const pay = () => {
    createPayment.mutate(id, {
      onSuccess: (payment) =>
        confirm.mutate(payment.provider_payment_id, {
          onSuccess: () => navigate("/pay/success"),
          onError: () => navigate("/pay/error"),
        }),
      onError: () => navigate("/pay/error"),
    });
  };

  const s = session.data;
  const activeTariff = tariffs.data?.find((t) => t.is_active) ?? null;
  const due = s ? amountDue(s, activeTariff) : 0;

  return (
    <div className="mx-auto max-w-md space-y-6">
      <div className="text-center">
        <div className="eyebrow">Оплата парковки</div>
        <h2 className="font-display text-xl font-semibold text-ink">
          Оплата сессии
        </h2>
      </div>

      <div className="card space-y-5 p-6">
        {session.isLoading ? (
          <p className="py-6 text-center text-ink-500/50">Загрузка…</p>
        ) : !s ? (
          <p className="py-6 text-center text-rose-500">Сессия не найдена</p>
        ) : (
          <>
            <div className="flex flex-col items-center gap-4">
              <PlateReadout plate={s.plate_number} size="lg" />
              <div className="text-center">
                <div className="eyebrow">К оплате</div>
                <div className="font-display text-3xl font-bold text-ink">
                  {formatMoney(due)}
                </div>
                {s.paid_amount > 0 && due > 0 && (
                  <div className="mt-1 text-xs text-ink-500/60">
                    доплата · уже оплачено {formatMoney(s.paid_amount)}
                  </div>
                )}
              </div>
            </div>

            {s.status === "paid" || due <= 0 ? (
              <p className="rounded-lg bg-emerald-50 py-3 text-center text-sm font-medium text-emerald-700">
                {s.status === "paid"
                  ? "Оплачено ✓"
                  : "Долга нет — можно выезжать ✓"}
              </p>
            ) : (
              <button
                onClick={pay}
                disabled={paying}
                className="w-full rounded-lg bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-50"
              >
                {paying ? "Оплата…" : "Оплатить (mock)"}
              </button>
            )}

            <p className="text-center text-xs text-ink-500/50">
              Демо-оплата без реального провайдера (Kaspi / Freedom подключаются
              позже по тому же интерфейсу).
            </p>
          </>
        )}
      </div>
    </div>
  );
}
