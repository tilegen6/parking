import { useNavigate, useParams } from "react-router-dom";
import {
  useConfirmPaymentMock,
  useCreatePayment,
  useSession,
  useTariffs,
} from "../api/hooks";
import { PaymentPanel } from "../components/PaymentPanel";
import { PlateReadout } from "../components/PlateReadout";
import { amountDue } from "../lib/tariff";

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

      <div className="card p-6">
        {session.isLoading ? (
          <p className="py-6 text-center text-ink-500/50">Загрузка…</p>
        ) : !s ? (
          <p className="py-6 text-center text-rose-500">Сессия не найдена</p>
        ) : s.status === "paid" || due <= 0 ? (
          <div className="flex flex-col items-center gap-4 py-2">
            <PlateReadout plate={s.plate_number} size="lg" />
            <p className="rounded-lg bg-emerald-50 px-4 py-3 text-center text-sm font-medium text-emerald-700">
              {s.status === "paid"
                ? "Оплачено ✓"
                : "Долга нет — можно выезжать ✓"}
            </p>
          </div>
        ) : (
          <PaymentPanel
            plate={s.plate_number}
            amount={due}
            paidAmount={s.paid_amount}
            onPay={pay}
            paying={paying}
          />
        )}
      </div>
    </div>
  );
}
