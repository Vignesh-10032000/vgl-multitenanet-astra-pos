// Display tender amounts without converting money to floating point.
export function moneyFromCents(cents) {
  return `${cents / 100n}.${String(cents % 100n).padStart(2, "0")}`;
}

export function paymentSummary(total, payments) {
  const cents = (value) => {
    const match = String(value || "0").match(/^(\d{1,12})(?:\.(\d{0,2}))?$/);
    if (!match) throw new Error("Enter a valid payment amount with up to two decimals.");
    return BigInt(match[1]) * 100n + BigInt((match[2] || "").padEnd(2, "0"));
  };
  const due = cents(total);
  const received = payments.reduce((sum, payment) => sum + cents(payment.amount), 0n);
  return {
    received: moneyFromCents(received),
    balance: moneyFromCents(due > received ? due - received : 0n),
    change: moneyFromCents(received > due ? received - due : 0n),
  };
}
