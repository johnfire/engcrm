// Euro amounts as the web shows and takes them: German style, 2.400,50 €, a whole
// amount without cents (the web's `eur` filter, gcrm/api/templates.py).

/** "2.400,50" for 2400.5, "2.400" for 2400; the amount as given when it is not a number. */
export function formatAmount(value: string | number | null | undefined): string {
  const amount = Number(value ?? 0);
  if (!Number.isFinite(amount)) return String(value);
  const whole = Number.isInteger(amount);
  const [integer, cents] = Math.abs(amount).toFixed(whole ? 0 : 2).split(".");
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${amount < 0 ? "-" : ""}${grouped}${cents ? `,${cents}` : ""}`;
}

/** "2.400,50 €". */
export function formatEur(value: string | number | null | undefined): string {
  return `${formatAmount(value)} €`;
}

/** A typed amount as the server takes it ("2400.50"), or null when it is not an
 *  amount above 0. A comma is the decimal mark, as on the web: "2400,50". */
export function typedAmount(text: string): string | null {
  const typed = text.trim().replace(",", ".");
  if (!/^\d{1,9}(\.\d{1,2})?$/.test(typed)) return null;
  return Number(typed) > 0 ? typed : null;
}
