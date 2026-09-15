import { formatMoney } from "../lib/tariff";
import { PlateReadout } from "./PlateReadout";
import { QrPlaceholder } from "./QrPlaceholder";

// Экран оплаты: плашка + сумма + QR + кнопка. Кнопка эмулирует приход webhook.
export function PaymentPanel({
  plate,
  amount,
  currency = "KZT",
  paidAmount = 0,
  onPay,
  paying,
}: {
  plate: string;
  amount: number;
  currency?: string;
  paidAmount?: number;
  onPay: () => void;
  paying: boolean;
}) {
  return (
    <div className="space-y-5">
      <div className="flex flex-col items-center gap-4">
        <PlateReadout plate={plate} size="lg" />
        <div className="text-center">
          <div className="eyebrow">К оплате</div>
          <div className="font-display text-3xl font-bold text-ink">
            {formatMoney(amount, currency)}
          </div>
          {paidAmount > 0 && (
            <div className="mt-1 text-xs text-ink-500/60">
              доплата · уже оплачено {formatMoney(paidAmount)}
            </div>
          )}
        </div>
        <QrPlaceholder value={`pay:${plate}:${amount}`} />
        <p className="text-center text-xs text-ink-500/50">
          Отсканируйте QR в приложении банка (в проде — Kaspi / Freedom).
        </p>
      </div>

      <button
        onClick={onPay}
        disabled={paying}
        className="w-full rounded-lg bg-brand px-4 py-3 text-sm font-semibold text-white transition hover:bg-brand-dark disabled:opacity-50"
      >
        {paying ? "Оплата…" : "Оплатить"}
      </button>
      <p className="text-center text-[11px] text-ink-500/40">
        mock: кнопка эмулирует приход webhook об оплате
      </p>
    </div>
  );
}
