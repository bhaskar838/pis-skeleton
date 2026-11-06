/**
 * Locale-aware formatting (SPEC §9.4): Indian digit grouping for INR tenants, dates in the tenant timezone.
 */

export interface TenantLocale {
  currency?: string | null;
  timezone?: string | null;
}

export function numberLocale(locale: TenantLocale): string {
  return locale.currency === "INR" ? "en-IN" : "en-GB";
}

export function formatNumber(value: number, locale: TenantLocale = {}): string {
  return new Intl.NumberFormat(numberLocale(locale)).format(value);
}

/** Amounts are stored in minor units (SPEC §6.3 money). */
export function formatMoneyMinor(amountMinor: number, currency: string, locale: TenantLocale = {}): string {
  const digits = new Intl.NumberFormat("en", { style: "currency", currency }).resolvedOptions().maximumFractionDigits ?? 2;
  return new Intl.NumberFormat(numberLocale({ ...locale, currency }), { style: "currency", currency }).format(
    amountMinor / 10 ** digits,
  );
}

export function formatDateTime(iso: string, locale: TenantLocale = {}): string {
  const tz = locale.timezone ?? "UTC";
  return new Intl.DateTimeFormat(numberLocale(locale), {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: tz,
  }).format(new Date(iso));
}

export function relativeTime(iso: string, now: Date = new Date()): string {
  const seconds = Math.round((new Date(iso).getTime() - now.getTime()) / 1000);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  const units: [Intl.RelativeTimeFormatUnit, number][] = [
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ];
  for (const [unit, size] of units) {
    if (Math.abs(seconds) >= size) return rtf.format(Math.round(seconds / size), unit);
  }
  return rtf.format(seconds, "second");
}
