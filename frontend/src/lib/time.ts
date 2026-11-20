// All display and "today" logic runs in Africa/Johannesburg whatever the device time
// zone (rules 5.5, 5.16). The API sends instants as UTC and dates as local YYYY-MM-DD.
// Raw UTC is never shown to users.

export const TIME_ZONE = "Africa/Johannesburg";

/** Number of days in the booking window: today + 6 (rule 5.5). */
export const BOOKING_WINDOW_DAYS = 7;

const timeFormat = new Intl.DateTimeFormat("en-ZA", {
  timeZone: TIME_ZONE,
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

const dateFormat = new Intl.DateTimeFormat("en-ZA", {
  timeZone: TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
});

const dateTimeFormat = new Intl.DateTimeFormat("en-ZA", {
  timeZone: TIME_ZONE,
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

// Formats a calendar date that is already a local date. It is built at UTC midnight and
// printed in UTC, which keeps the calendar day unchanged on any device.
const calendarDateFormat = new Intl.DateTimeFormat("en-ZA", {
  timeZone: "UTC",
  weekday: "short",
  day: "numeric",
  month: "short",
  year: "numeric",
});

// en-CA prints numeric dates as YYYY-MM-DD.
const isoDateFormat = new Intl.DateTimeFormat("en-CA", {
  timeZone: TIME_ZONE,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
});

function toDate(instant: string | Date): Date {
  return instant instanceof Date ? instant : new Date(instant);
}

function parseCalendarDate(date: string): Date {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date);
  if (!match) throw new Error(`Invalid calendar date: ${date}`);
  return new Date(Date.UTC(Number(match[1]), Number(match[2]) - 1, Number(match[3])));
}

/** An instant as local clock time, for example "08:00". */
export function formatTime(instant: string | Date): string {
  return timeFormat.format(toDate(instant));
}

/** The local calendar date of an instant, for example "Thu, 19 Nov 2026". */
export function formatInstantDate(instant: string | Date): string {
  return dateFormat.format(toDate(instant));
}

/** An instant as local date and time, for example "Thu, 19 Nov 2026, 08:00". */
export function formatDateTime(instant: string | Date): string {
  return dateTimeFormat.format(toDate(instant));
}

/** A `YYYY-MM-DD` calendar date (already local), for example "Thu, 19 Nov 2026". */
export function formatDate(date: string): string {
  return calendarDateFormat.format(parseCalendarDate(date));
}

/** The `YYYY-MM-DD` local date of an instant. */
export function localDateOf(instant: string | Date): string {
  return isoDateFormat.format(toDate(instant));
}

/** Today's `YYYY-MM-DD` date in Africa/Johannesburg. `now` is injectable for tests. */
export function todayLocal(now: Date = new Date()): string {
  return localDateOf(now);
}

/** `date` plus `days` calendar days, as `YYYY-MM-DD`. */
export function addDays(date: string, days: number): string {
  const d = parseCalendarDate(date);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

/** The 7 bookable dates, today to today + 6, as `YYYY-MM-DD` (rule 5.5). */
export function bookingWindowDates(now: Date = new Date()): string[] {
  const today = todayLocal(now);
  return Array.from({ length: BOOKING_WINDOW_DAYS }, (_, i) => addDays(today, i));
}
