const PERSIAN_LOCALE = "fa-IR-u-ca-persian";

const DATE_FORMATTER = new Intl.DateTimeFormat(PERSIAN_LOCALE, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

const DATE_TIME_FORMATTER = new Intl.DateTimeFormat(PERSIAN_LOCALE, {
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit",
  hour12: false,
});

function parseDate(value: unknown): Date | null {
  if (!value) return null;
  if (value instanceof Date) {
    return Number.isNaN(value.getTime()) ? null : value;
  }
  const raw = String(value).trim();
  if (!raw) return null;
  const parsed = new Date(raw);
  return Number.isNaN(parsed.getTime()) ? null : parsed;
}

export function formatShamsiDate(value: unknown, fallback = "-"): string {
  const date = parseDate(value);
  if (!date) return fallback;
  return DATE_FORMATTER.format(date);
}

export function formatShamsiDateTime(value: unknown, fallback = "-"): string {
  const date = parseDate(value);
  if (!date) return fallback;
  return DATE_TIME_FORMATTER.format(date);
}

export function formatShamsiDateForFileName(value: unknown): string {
  const formatted = formatShamsiDate(value, "");
  if (!formatted) return "date";
  return formatted.replace(/[\\/:*?"<>|]/g, "-").replace(/\s+/g, "_");
}

