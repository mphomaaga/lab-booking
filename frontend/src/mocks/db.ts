// In-memory data and business rules for the mock API. Everything lives in module state, so
// it starts fresh on every page reload (no persistence by design).
//
// Rules mirrored from docs/api.yaml: 5.1/5.2 opening hours, 5.3 labs, 5.5 booking window,
// 5.6 daily limit, 5.7 no overlap, 5.8 full and started slots, 5.9 cancelling, 5.10 closures,
// 5.12 inactive labs, 5.13 admins, 5.16 Africa/Johannesburg dates.
import type {
  AdminBooking,
  AdminDayBookings,
  Booking,
  ClosureCreated,
  DaySlots,
  Lab,
  LoginResponse,
  Slot,
  SlotRef,
  User,
} from "../api/types";
import { BOOKING_WINDOW_DAYS, addDays, localDateOf, todayLocal } from "../lib/time";
import { MockHttpError, notAuthenticated } from "./errors";

// ---------------------------------------------------------------------------
// Types and seed data
// ---------------------------------------------------------------------------

export interface UserRecord extends User {
  password: string;
}

interface LabRecord extends Lab {
  is_active: boolean;
}

interface SlotRecord {
  id: number;
  labId: number;
  startMs: number;
}

interface BookingRecord {
  id: number;
  userId: number;
  slotId: number;
  createdAt: Date;
  cancelledAt: Date | null;
}

interface ClosureRecord {
  id: number;
  labId: number;
  date: string;
  createdAt: Date;
}

// Rule 5.3.
const labs: LabRecord[] = [
  { id: 1, name: "Lab A", seats: 30, is_active: true },
  { id: 2, name: "Lab B", seats: 30, is_active: true },
  { id: 3, name: "Lab C", seats: 30, is_active: true },
];

// Same accounts as backend/seed_data/accounts.sample.csv (docs/data-model.md "Seed data").
const users: UserRecord[] = [
  { id: 1, student_number: "20260001", password: "student-pass-1", is_admin: false },
  { id: 2, student_number: "20260002", password: "student-pass-2", is_admin: false },
  { id: 3, student_number: "20260003", password: "student-pass-3", is_admin: false },
  { id: 4, student_number: "90000001", password: "admin-pass-1", is_admin: true },
];

const slots = new Map<number, SlotRecord>();
const slotKeys = new Map<string, SlotRecord>();
const bookings: BookingRecord[] = [];
const closures: ClosureRecord[] = [];

let nextSlotId = 1;
let nextBookingId = 1;
let nextClosureId = 1;

// ---------------------------------------------------------------------------
// Time helpers
// ---------------------------------------------------------------------------

const HOUR_MS = 60 * 60 * 1000;
const OPENING_HOUR = 8; // rule 5.2: first slot starts at local 08:00
const SLOTS_PER_DAY = 10; // 08:00 .. 17:00 starts
// Africa/Johannesburg is UTC+2 all year (no daylight saving).
const LOCAL_UTC_OFFSET_HOURS = 2;
const TOKEN_LIFETIME_MS = 480 * 60 * 1000; // JWT_EXPIRE_MINUTES default (rule 5.14)

/** ISO 8601 UTC with whole seconds and a Z suffix, as the contract requires. */
function iso(value: Date | number): string {
  return new Date(value).toISOString().replace(/\.\d{3}Z$/, "Z");
}

function parseDate(date: string): { year: number; month: number; day: number } {
  const [year, month, day] = date.split("-").map(Number);
  return { year, month, day };
}

function isWeekend(date: string): boolean {
  const { year, month, day } = parseDate(date);
  const weekday = new Date(Date.UTC(year, month - 1, day)).getUTCDay();
  return weekday === 0 || weekday === 6;
}

/** True for a real `YYYY-MM-DD` calendar date. */
export function isValidDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const { year, month, day } = parseDate(value);
  const d = new Date(Date.UTC(year, month - 1, day));
  return d.getUTCFullYear() === year && d.getUTCMonth() === month - 1 && d.getUTCDate() === day;
}

function inBookingWindow(date: string, now: Date): boolean {
  const today = todayLocal(now);
  return date >= today && date <= addDays(today, BOOKING_WINDOW_DAYS - 1);
}

function slotDate(slot: SlotRecord): string {
  return localDateOf(new Date(slot.startMs));
}

// ---------------------------------------------------------------------------
// Lookups and shaping
// ---------------------------------------------------------------------------

function activeLab(labId: number): LabRecord {
  const lab = labs.find((l) => l.id === labId && l.is_active);
  if (!lab) throw new MockHttpError(404, "lab_not_found", "Lab not found.");
  return lab;
}

/** Bookings keep their lab even if it later became inactive, so this ignores `is_active`. */
function labById(labId: number): LabRecord {
  return labs.find((l) => l.id === labId)!;
}

function publicLab(lab: LabRecord): Lab {
  return { id: lab.id, name: lab.name, seats: lab.seats };
}

function publicUser(user: UserRecord): User {
  return { id: user.id, student_number: user.student_number, is_admin: user.is_admin };
}

function isClosed(labId: number, date: string): boolean {
  return closures.some((c) => c.labId === labId && c.date === date);
}

function activeBookingsForSlot(slotId: number): BookingRecord[] {
  return bookings.filter((b) => b.slotId === slotId && b.cancelledAt === null);
}

function slotOf(booking: BookingRecord): SlotRecord {
  return slots.get(booking.slotId)!;
}

function publicSlot(slot: SlotRecord, lab: LabRecord, now: Date): Slot {
  const free = Math.max(0, lab.seats - activeBookingsForSlot(slot.id).length);
  return {
    id: slot.id,
    start_time: iso(slot.startMs),
    end_time: iso(slot.startMs + HOUR_MS),
    seats: lab.seats,
    free_seats: free,
    bookable: slot.startMs > now.getTime() && free > 0,
  };
}

function slotRef(slot: SlotRecord): SlotRef {
  return { id: slot.id, start_time: iso(slot.startMs), end_time: iso(slot.startMs + HOUR_MS) };
}

function publicBooking(booking: BookingRecord, now: Date): Booking {
  const slot = slotOf(booking);
  const lab = labById(slot.labId);
  const active = booking.cancelledAt === null;
  return {
    id: booking.id,
    status: active ? "active" : "cancelled",
    created_at: iso(booking.createdAt),
    cancelled_at: booking.cancelledAt ? iso(booking.cancelledAt) : null,
    cancellable: active && slot.startMs > now.getTime(),
    lab: { id: lab.id, name: lab.name },
    slot: slotRef(slot),
  };
}

function byStartThenCreated(a: BookingRecord, b: BookingRecord): number {
  return (
    slotOf(a).startMs - slotOf(b).startMs ||
    a.createdAt.getTime() - b.createdAt.getTime() ||
    a.id - b.id
  );
}

/** Slot rows are created on demand the first time an open date is requested. */
function ensureSlots(lab: LabRecord, date: string): SlotRecord[] {
  const { year, month, day } = parseDate(date);
  const result: SlotRecord[] = [];
  for (let i = 0; i < SLOTS_PER_DAY; i++) {
    const key = `${lab.id}|${date}|${i}`;
    let slot = slotKeys.get(key);
    if (!slot) {
      const startMs = Date.UTC(year, month - 1, day, OPENING_HOUR + i - LOCAL_UTC_OFFSET_HOURS);
      slot = { id: nextSlotId++, labId: lab.id, startMs };
      slotKeys.set(key, slot);
      slots.set(slot.id, slot);
    }
    result.push(slot);
  }
  return result;
}

// ---------------------------------------------------------------------------
// Auth
// ---------------------------------------------------------------------------

// The token carries the user id and expiry, so it stays valid across a page reload (the
// users never change) and an expired or garbled one gives 401 like the real API.
const TOKEN_PATTERN = /^mock-token\.(\d+)\.(\d+)$/;

export function login(studentNumber: string, password: string, now = new Date()): LoginResponse {
  const user = users.find((u) => u.student_number === studentNumber);
  if (!user || user.password !== password) {
    throw new MockHttpError(401, "invalid_credentials", "Student number or password is incorrect.");
  }
  const expiresAt = Math.floor((now.getTime() + TOKEN_LIFETIME_MS) / 1000) * 1000;
  return {
    access_token: `mock-token.${user.id}.${expiresAt}`,
    token_type: "bearer",
    expires_at: iso(expiresAt),
    user: publicUser(user),
  };
}

/** The user behind an `Authorization` header, or 401 `not_authenticated`. */
export function authenticate(header: string | null, now = new Date()): UserRecord {
  const match = header ? /^Bearer (\S+)$/.exec(header) : null;
  const parts = match ? TOKEN_PATTERN.exec(match[1]) : null;
  if (!parts) throw notAuthenticated();
  const user = users.find((u) => u.id === Number(parts[1]));
  if (!user || Number(parts[2]) <= now.getTime()) throw notAuthenticated();
  return user;
}

export function requireAdmin(user: UserRecord): void {
  if (!user.is_admin) throw new MockHttpError(403, "admin_required", "Admins only.");
}

export function me(user: UserRecord): User {
  return publicUser(user);
}

// ---------------------------------------------------------------------------
// Labs and slots
// ---------------------------------------------------------------------------

export function listLabs(): Lab[] {
  return labs
    .filter((l) => l.is_active)
    .sort((a, b) => a.name.localeCompare(b.name))
    .map(publicLab);
}

export function getLabSlots(labId: number, date: string, now = new Date()): DaySlots {
  const lab = activeLab(labId); // 1. 404 lab_not_found
  if (!inBookingWindow(date, now)) {
    // 2. rule 5.5
    throw new MockHttpError(422, "date_out_of_window", "You can only view today and the next 6 days.");
  }
  const base = { lab: publicLab(lab), date };
  if (isWeekend(date)) return { ...base, day_status: "weekend", slots: [] }; // 3. rule 5.1
  if (isClosed(lab.id, date)) return { ...base, day_status: "closed", slots: [] }; // 4. rule 5.10
  return {
    ...base,
    day_status: "open", // 5.
    slots: ensureSlots(lab, date).map((s) => publicSlot(s, lab, now)),
  };
}

// ---------------------------------------------------------------------------
// Bookings
// ---------------------------------------------------------------------------

export function createBooking(user: UserRecord, slotId: number, now = new Date()): Booking {
  const slot = slots.get(slotId);
  const lab = slot ? labs.find((l) => l.id === slot.labId && l.is_active) : undefined;
  if (!slot || !lab) throw new MockHttpError(404, "slot_not_found", "Slot not found."); // 1

  if (slot.startMs <= now.getTime()) {
    throw new MockHttpError(422, "slot_in_past", "This slot has already started."); // 2
  }
  const date = slotDate(slot);
  if (!inBookingWindow(date, now)) {
    throw new MockHttpError(
      422,
      "outside_booking_window",
      "You can only book today and the next 6 days.",
    ); // 3
  }
  if (isClosed(lab.id, date)) {
    throw new MockHttpError(409, "lab_closed", "This lab is closed on that date."); // 4
  }

  // Cancelled bookings never count towards checks 5 to 8.
  const mine = bookings.filter((b) => b.userId === user.id && b.cancelledAt === null);
  if (mine.some((b) => b.slotId === slot.id)) {
    throw new MockHttpError(409, "already_booked", "You already booked this slot."); // 5
  }
  if (mine.some((b) => slotOf(b).startMs === slot.startMs && slotOf(b).labId !== slot.labId)) {
    throw new MockHttpError(
      409,
      "overlapping_booking",
      "You already have a booking in another lab at this time.",
    ); // 6
  }
  if (mine.filter((b) => slotDate(slotOf(b)) === date).length >= 2) {
    throw new MockHttpError(409, "daily_limit_reached", "You already have 2 bookings on this day."); // 7
  }
  if (activeBookingsForSlot(slot.id).length >= lab.seats) {
    throw new MockHttpError(409, "slot_full", "This slot is full."); // 8
  }

  const booking: BookingRecord = {
    id: nextBookingId++,
    userId: user.id,
    slotId: slot.id,
    createdAt: now,
    cancelledAt: null,
  };
  bookings.push(booking);
  return publicBooking(booking, now);
}

export function cancelBooking(user: UserRecord, bookingId: number, now = new Date()): Booking {
  const booking = bookings.find((b) => b.id === bookingId);
  if (!booking) throw new MockHttpError(404, "booking_not_found", "Booking not found."); // 1
  if (booking.userId !== user.id) {
    throw new MockHttpError(403, "not_your_booking", "You can only cancel your own bookings."); // 2
  }
  if (booking.cancelledAt !== null) {
    throw new MockHttpError(409, "booking_already_cancelled", "This booking is already cancelled."); // 3
  }
  if (slotOf(booking).startMs <= now.getTime()) {
    throw new MockHttpError(
      409,
      "booking_already_started",
      "This booking has already started and can't be cancelled.",
    ); // 4
  }
  booking.cancelledAt = now;
  return publicBooking(booking, now);
}

export function listMyBookings(user: UserRecord, now = new Date()): Booking[] {
  return bookings
    .filter((b) => b.userId === user.id && slotOf(b).startMs + HOUR_MS > now.getTime())
    .sort(byStartThenCreated)
    .map((b) => publicBooking(b, now));
}

// ---------------------------------------------------------------------------
// Admin (the 403 check is done by the handler through `requireAdmin`)
// ---------------------------------------------------------------------------

/** 404 `lab_not_found` for a missing or inactive lab; exported so handlers can order checks. */
export function assertActiveLab(labId: number): void {
  activeLab(labId);
}

export function adminListBookings(labId: number, date: string): AdminDayBookings {
  const lab = activeLab(labId);
  const list: AdminBooking[] = bookings
    .filter((b) => slotOf(b).labId === lab.id && slotDate(slotOf(b)) === date)
    .sort(byStartThenCreated)
    .map((b) => {
      const user = users.find((u) => u.id === b.userId)!;
      return {
        id: b.id,
        status: b.cancelledAt === null ? "active" : "cancelled",
        created_at: iso(b.createdAt),
        cancelled_at: b.cancelledAt ? iso(b.cancelledAt) : null,
        slot: slotRef(slotOf(b)),
        user: { id: user.id, student_number: user.student_number },
      };
    });
  return { lab: publicLab(lab), date, closed: isClosed(lab.id, date), bookings: list };
}

/** 422 `closure_date_in_past`, 409 `closure_exists`, then closes and cancels (rule 5.10). */
export function createClosure(labId: number, date: string, now = new Date()): ClosureCreated {
  const lab = activeLab(labId);
  if (date < todayLocal(now)) {
    throw new MockHttpError(422, "closure_date_in_past", "You can't close a lab for a date in the past.");
  }
  if (isClosed(lab.id, date)) {
    throw new MockHttpError(409, "closure_exists", "This lab is already closed on that date.");
  }
  const closure: ClosureRecord = { id: nextClosureId++, labId: lab.id, date, createdAt: now };
  closures.push(closure);

  // Cancel active bookings that have not started; leave started and finished ones alone.
  let cancelled = 0;
  for (const b of bookings) {
    const slot = slotOf(b);
    if (
      b.cancelledAt === null &&
      slot.labId === lab.id &&
      slotDate(slot) === date &&
      slot.startMs > now.getTime()
    ) {
      b.cancelledAt = now;
      cancelled++;
    }
  }
  return {
    id: closure.id,
    lab_id: lab.id,
    date,
    created_at: iso(now),
    cancelled_booking_count: cancelled,
  };
}
