function decimalParts(value) {
  const match = String(value ?? "").trim().match(/^(-?)(\d+)(?:\.(\d+))?$/);
  if (!match) throw new Error("Value must be a finite decimal number.");
  return { negative: match[1] === "-", whole: match[2], fraction: match[3] || "" };
}

export function decimalToScaled(value, scale) {
  const parts = decimalParts(value);
  const factor = 10n ** BigInt(scale);
  const kept = parts.fraction.slice(0, scale).padEnd(scale, "0");
  const discarded = parts.fraction.slice(scale);
  let result = BigInt(parts.whole) * factor + BigInt(kept || "0");
  if (discarded && discarded[0] >= "5") result += 1n;
  return parts.negative ? -result : result;
}

export function scaledToDecimal(value, scale) {
  const negative = value < 0n;
  const absolute = negative ? -value : value;
  const factor = 10n ** BigInt(scale);
  const whole = absolute / factor;
  const fraction = String(absolute % factor).padStart(scale, "0");
  return `${negative ? "-" : ""}${whole}.${fraction}`;
}

function divideHalfUp(numerator, denominator) {
  if (denominator <= 0n) throw new Error("Denominator must be positive.");
  const negative = numerator < 0n;
  const absolute = negative ? -numerator : numerator;
  const quotient = absolute / denominator;
  const remainder = absolute % denominator;
  const rounded = quotient + (remainder * 2n >= denominator ? 1n : 0n);
  return negative ? -rounded : rounded;
}

function apportion(total, weights) {
  if (!weights.length) {
    if (total === 0n) return [];
    throw new Error("At least one weight is required for a non-zero total.");
  }
  if (weights.some((weight) => weight < 0n)) {
    throw new Error("Apportionment weights cannot be negative.");
  }
  if (total === 0n) return weights.map(() => 0n);
  const sum = weights.reduce((result, weight) => result + weight, 0n);
  if (sum === 0n) throw new Error("Apportionment weights must contain a positive value.");
  const negative = total < 0n;
  const absolute = negative ? -total : total;
  const floors = weights.map((weight) => (absolute * weight) / sum);
  const remainders = weights.map((weight) => (absolute * weight) % sum);
  let remaining = absolute - floors.reduce((result, value) => result + value, 0n);
  const indexes = weights.map((_, index) => index).sort((left, right) => {
    if (remainders[left] === remainders[right]) return left - right;
    return remainders[left] > remainders[right] ? -1 : 1;
  });
  for (const index of indexes) {
    if (remaining === 0n) break;
    floors[index] += 1n;
    remaining -= 1n;
  }
  return floors.map((value) => (negative ? -value : value));
}

function prepareLine(line, index) {
  const quantity = decimalToScaled(line.quantity, 3);
  if (quantity <= 0n) throw new Error(`Line ${index} quantity must be greater than zero.`);
  const unitPrice = decimalToScaled(line.unit_price, 2);
  const taxRate = decimalToScaled(line.tax_rate, 2);
  const cessRate = decimalToScaled(line.cess_rate || "0.00", 2);
  const lineDiscount = decimalToScaled(line.line_discount || "0.00", 2);
  if (unitPrice < 0n) throw new Error(`Line ${index} unit price cannot be negative.`);
  if (taxRate < 0n || taxRate > 10000n) {
    throw new Error(`Line ${index} tax rate must be between 0 and 100.`);
  }
  if (cessRate < 0n || cessRate > 10000n) {
    throw new Error(`Line ${index} cess rate must be between 0 and 100.`);
  }
  const gross = divideHalfUp(quantity * unitPrice, 1000n);
  if (lineDiscount < 0n || lineDiscount > gross) {
    throw new Error(`Line ${index} line discount cannot exceed line gross.`);
  }
  if (typeof line.tax_inclusive !== "boolean") {
    throw new Error(`Line ${index} tax-inclusive flag must be boolean.`);
  }
  return {
    quantity,
    unitPrice,
    taxRate,
    cessRate,
    taxInclusive: line.tax_inclusive,
    gross,
    lineDiscount,
    discountable: gross - lineDiscount,
  };
}

function calculateLine(line, orderDiscount, interstate) {
  const discountedValue = line.discountable - orderDiscount;
  let taxable;
  let gst;
  let cess;
  if (line.taxInclusive) {
    taxable = divideHalfUp(
      discountedValue * 10000n,
      10000n + line.taxRate + line.cessRate,
    );
    [gst, cess] = apportion(discountedValue - taxable, [line.taxRate, line.cessRate]);
  } else {
    taxable = discountedValue;
    gst = divideHalfUp(taxable * line.taxRate, 10000n);
    cess = divideHalfUp(taxable * line.cessRate, 10000n);
  }
  const cgst = interstate ? 0n : gst / 2n;
  const sgst = interstate ? 0n : gst - cgst;
  const igst = interstate ? gst : 0n;
  const total = taxable + cgst + sgst + igst + cess;
  return {
    quantity: scaledToDecimal(line.quantity, 3),
    unit_price: scaledToDecimal(line.unitPrice, 2),
    gross_amount: scaledToDecimal(line.gross, 2),
    discount_amount: scaledToDecimal(line.lineDiscount + orderDiscount, 2),
    taxable_amount: scaledToDecimal(taxable, 2),
    tax_rate: scaledToDecimal(line.taxRate, 2),
    cess_rate: scaledToDecimal(line.cessRate, 2),
    cgst_amount: scaledToDecimal(cgst, 2),
    sgst_amount: scaledToDecimal(sgst, 2),
    igst_amount: scaledToDecimal(igst, 2),
    cess_amount: scaledToDecimal(cess, 2),
    total_amount: scaledToDecimal(total, 2),
    _values: { taxable, cgst, sgst, igst, cess, total },
  };
}

export function computeTax(input) {
  if (!Array.isArray(input.lines) || !input.lines.length) {
    throw new Error("At least one tax line is required.");
  }
  const prepared = input.lines.map((line, index) => prepareLine(line, index + 1));
  const orderDiscount = decimalToScaled(input.order_discount || "0.00", 2);
  const discountable = prepared.reduce((total, line) => total + line.discountable, 0n);
  if (orderDiscount < 0n || orderDiscount > discountable) {
    throw new Error("Order discount cannot exceed the order value.");
  }
  const interstate = String(input.supplier_state).trim() !== String(input.place_of_supply).trim();
  const allocated = apportion(orderDiscount, prepared.map((line) => line.discountable));
  const lines = prepared.map((line, index) => calculateLine(line, allocated[index], interstate));
  const sum = (key) => lines.reduce((total, line) => total + line._values[key], 0n);
  const gross = prepared.reduce((total, line) => total + line.gross, 0n);
  const lineDiscount = prepared.reduce((total, line) => total + line.lineDiscount, 0n);
  const taxable = sum("taxable");
  const cgst = sum("cgst");
  const sgst = sum("sgst");
  const igst = sum("igst");
  const cess = sum("cess");
  const beforeRoundOff = taxable + cgst + sgst + igst + cess;
  const net = input.apply_round_off === false
    ? beforeRoundOff
    : divideHalfUp(beforeRoundOff, 100n) * 100n;
  const roundOff = net - beforeRoundOff;
  return {
    lines: lines.map(({ _values, ...line }) => line),
    is_interstate: interstate,
    gross_amount: scaledToDecimal(gross, 2),
    discount_amount: scaledToDecimal(lineDiscount + orderDiscount, 2),
    taxable_amount: scaledToDecimal(taxable, 2),
    cgst_amount: scaledToDecimal(cgst, 2),
    sgst_amount: scaledToDecimal(sgst, 2),
    igst_amount: scaledToDecimal(igst, 2),
    cess_amount: scaledToDecimal(cess, 2),
    round_off: scaledToDecimal(roundOff, 2),
    net_amount: scaledToDecimal(net, 2),
  };
}

export function computePaymentPreview(quote, payments) {
  const normalized = payments.map((payment) => ({
    method: String(payment.method).toUpperCase(),
    amount: decimalToScaled(payment.amount, 2),
  }));
  if (!normalized.length || normalized.some((payment) => payment.amount <= 0n)) {
    throw new Error("At least one positive payment is required.");
  }
  const received = normalized.reduce((total, payment) => total + payment.amount, 0n);
  const payable = decimalToScaled(quote.net_amount, 2);
  const change = received > payable ? received - payable : 0n;
  const balance = payable > received ? payable - received : 0n;
  const cash = normalized
    .filter((payment) => payment.method === "CASH")
    .reduce((total, payment) => total + payment.amount, 0n);
  if (change > cash) throw new Error("Change cannot be funded by a non-cash payment.");
  return {
    ...quote,
    amount_received: scaledToDecimal(received, 2),
    change_due: scaledToDecimal(change, 2),
    balance_due: scaledToDecimal(balance, 2),
  };
}
