// One typed function per operation in docs/api.yaml. Screens never call fetch directly.
import { clearToken, getToken } from "../auth/tokenStorage";
import { ApiError } from "./errors";
import type {
  AdminDayBookings,
  Booking,
  ClosureCreated,
  CreateBookingRequest,
  CreateClosureRequest,
  DaySlots,
  Error as ErrorResponse,
  Lab,
  LoginRequest,
  LoginResponse,
  User,
} from "./types";

export { ApiError, errorMessage } from "./errors";

const DEFAULT_BASE_URL = "http://localhost:8000";

const BASE_URL: string = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || DEFAULT_BASE_URL
).replace(/\/+$/, "");

let onUnauthorized: (() => void) | null = null;

/** Called after a 401 from any call except `login`; the token is already cleared. */
export function setUnauthorizedHandler(handler: (() => void) | null): void {
  onUnauthorized = handler;
}

interface RequestOptions {
  method?: "GET" | "POST" | "DELETE";
  query?: Record<string, string | number>;
  body?: unknown;
  /** false for `login`, which has no token and returns its own 401 to the caller. */
  auth?: boolean;
}

function isErrorBody(value: unknown): value is ErrorResponse {
  if (typeof value !== "object" || value === null) return false;
  const error = (value as { error?: unknown }).error;
  if (typeof error !== "object" || error === null) return false;
  const { code, message } = error as { code?: unknown; message?: unknown };
  return typeof code === "string" && typeof message === "string";
}

async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = "GET", query, body, auth = true } = options;

  let url = BASE_URL + path;
  if (query) {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(query)) params.set(key, String(value));
    url += `?${params.toString()}`;
  }

  const headers: Record<string, string> = { Accept: "application/json" };
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth) {
    const token = getToken();
    if (token) headers.Authorization = `Bearer ${token}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "internal_error", "Can't reach the server. Check your connection and try again.");
  }

  let data: unknown = null;
  try {
    data = await response.json();
  } catch {
    data = null;
  }

  if (!response.ok) {
    if (response.status === 401 && auth) {
      clearToken();
      onUnauthorized?.();
    }
    if (isErrorBody(data)) {
      throw new ApiError(response.status, data.error.code, data.error.message);
    }
    throw new ApiError(response.status, "internal_error", "Something went wrong. Please try again.");
  }

  return data as T;
}

/** POST /auth/login. A 401 `invalid_credentials` is thrown to the caller, not handled here. */
export function login(student_number: string, password: string): Promise<LoginResponse> {
  const body: LoginRequest = { student_number, password };
  return request<LoginResponse>("/auth/login", { method: "POST", body, auth: false });
}

/** GET /me */
export function getMe(): Promise<User> {
  return request<User>("/me");
}

/** GET /labs */
export function listLabs(): Promise<Lab[]> {
  return request<Lab[]>("/labs");
}

/** GET /labs/{lab_id}/slots?date=YYYY-MM-DD */
export function getLabSlots(labId: number, date: string): Promise<DaySlots> {
  return request<DaySlots>(`/labs/${labId}/slots`, { query: { date } });
}

/** POST /bookings */
export function createBooking(slotId: number): Promise<Booking> {
  const body: CreateBookingRequest = { slot_id: slotId };
  return request<Booking>("/bookings", { method: "POST", body });
}

/** DELETE /bookings/{booking_id} */
export function cancelBooking(bookingId: number): Promise<Booking> {
  return request<Booking>(`/bookings/${bookingId}`, { method: "DELETE" });
}

/** GET /me/bookings */
export function listMyBookings(): Promise<Booking[]> {
  return request<Booking[]>("/me/bookings");
}

/** GET /admin/bookings?lab_id=&date= */
export function adminListBookings(labId: number, date: string): Promise<AdminDayBookings> {
  return request<AdminDayBookings>("/admin/bookings", { query: { lab_id: labId, date } });
}

/** POST /admin/labs/{lab_id}/closures */
export function adminCreateClosure(labId: number, date: string): Promise<ClosureCreated> {
  const body: CreateClosureRequest = { date };
  return request<ClosureCreated>(`/admin/labs/${labId}/closures`, { method: "POST", body });
}
