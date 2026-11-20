// MSW handlers for every operation in docs/api.yaml, at the contract paths under
// VITE_API_BASE_URL. Rules and data live in ./db.ts; this file does HTTP: auth, request
// validation and the error body shape.
//
// Check order per operation: 401 (token), 403 (admin), request validation, then the
// operation's own checks in the order the contract lists them. The admin operations list 404
// `lab_not_found` before `validation_error`, so those look up the lab (when its id is a
// valid integer) before they validate the rest of the request.
import { HttpResponse, http } from "msw";
import type { ErrorDetail } from "../api/types";
import * as db from "./db";
import { MockHttpError, validationError } from "./errors";

const DEFAULT_BASE_URL = "http://localhost:8000";

const BASE_URL: string = (
  (import.meta.env.VITE_API_BASE_URL as string | undefined) || DEFAULT_BASE_URL
).replace(/\/+$/, "");

interface Ctx {
  request: Request;
  params: Record<string, string | readonly string[] | undefined>;
}

/** Runs a handler and turns a `MockHttpError` into the contract's error body. */
function route(fn: (ctx: Ctx) => Response | Promise<Response>) {
  return async (ctx: Ctx): Promise<Response> => {
    try {
      return await fn(ctx);
    } catch (e) {
      if (e instanceof MockHttpError) {
        const error: { code: string; message: string; details?: ErrorDetail[] } = {
          code: e.code,
          message: e.message,
        };
        if (e.details) error.details = e.details;
        return HttpResponse.json({ error }, { status: e.status });
      }
      throw e;
    }
  };
}

function currentUser(request: Request): db.UserRecord {
  return db.authenticate(request.headers.get("Authorization"));
}

function currentAdmin(request: Request): db.UserRecord {
  const user = currentUser(request);
  db.requireAdmin(user);
  return user;
}

// --- Request validation -----------------------------------------------------------------

const INTEGER = /^-?\d+$/;

function intParam(
  raw: string | readonly string[] | null | undefined,
  loc: [string, string],
  details: ErrorDetail[],
): number | null {
  if (raw === null || raw === undefined) {
    details.push({ loc, msg: "Field required" });
    return null;
  }
  const text = Array.isArray(raw) ? raw[0] : (raw as string);
  if (!INTEGER.test(text)) {
    details.push({ loc, msg: "Input should be a valid integer, unable to parse string as an integer" });
    return null;
  }
  return Number(text);
}

function dateParam(
  raw: string | null | undefined,
  loc: [string, string],
  details: ErrorDetail[],
): string | null {
  if (raw === null || raw === undefined) {
    details.push({ loc, msg: "Field required" });
    return null;
  }
  if (!db.isValidDate(raw)) {
    details.push({ loc, msg: "Input should be a valid date or datetime, invalid character in year" });
    return null;
  }
  return raw;
}

function fail(details: ErrorDetail[]): void {
  if (details.length > 0) throw validationError(details);
}

/** Parses a JSON object body; anything else is a 422 `validation_error`. */
async function readBody(request: Request): Promise<Record<string, unknown>> {
  let body: unknown;
  try {
    body = await request.json();
  } catch {
    throw validationError([{ loc: ["body"], msg: "JSON decode error" }]);
  }
  if (typeof body !== "object" || body === null || Array.isArray(body)) {
    throw validationError([{ loc: ["body"], msg: "Input should be a valid dictionary or object" }]);
  }
  return body as Record<string, unknown>;
}

/** Every key of `body` must be in `allowed` (the contract sets additionalProperties: false). */
function rejectExtraKeys(body: Record<string, unknown>, allowed: string[], details: ErrorDetail[]): void {
  for (const key of Object.keys(body)) {
    if (!allowed.includes(key)) details.push({ loc: ["body", key], msg: "Extra inputs are not permitted" });
  }
}

function stringField(
  body: Record<string, unknown>,
  name: string,
  maxLength: number,
  details: ErrorDetail[],
): string | null {
  const value = body[name];
  if (value === undefined) {
    details.push({ loc: ["body", name], msg: "Field required" });
    return null;
  }
  if (typeof value !== "string") {
    details.push({ loc: ["body", name], msg: "Input should be a valid string" });
    return null;
  }
  if (value.length < 1) {
    details.push({ loc: ["body", name], msg: "String should have at least 1 character" });
    return null;
  }
  if (value.length > maxLength) {
    details.push({ loc: ["body", name], msg: `String should have at most ${maxLength} characters` });
    return null;
  }
  return value;
}

// --- Handlers ---------------------------------------------------------------------------

const handlers = [
  // health
  http.get(
    `${BASE_URL}/health`,
    route(() => HttpResponse.json({ status: "ok" })),
  ),

  // login
  http.post(
    `${BASE_URL}/auth/login`,
    route(async ({ request }) => {
      const body = await readBody(request);
      const details: ErrorDetail[] = [];
      const studentNumber = stringField(body, "student_number", 32, details);
      const password = stringField(body, "password", 128, details);
      rejectExtraKeys(body, ["student_number", "password"], details);
      fail(details);
      return HttpResponse.json(db.login(studentNumber!, password!));
    }),
  ),

  // getMe
  http.get(
    `${BASE_URL}/me`,
    route(({ request }) => HttpResponse.json(db.me(currentUser(request)))),
  ),

  // listLabs
  http.get(
    `${BASE_URL}/labs`,
    route(({ request }) => {
      currentUser(request);
      return HttpResponse.json(db.listLabs());
    }),
  ),

  // getLabSlots
  http.get(
    `${BASE_URL}/labs/:lab_id/slots`,
    route(({ request, params }) => {
      currentUser(request);
      const details: ErrorDetail[] = [];
      const labId = intParam(params.lab_id, ["path", "lab_id"], details);
      const date = dateParam(new URL(request.url).searchParams.get("date"), ["query", "date"], details);
      fail(details);
      return HttpResponse.json(db.getLabSlots(labId!, date!));
    }),
  ),

  // createBooking
  http.post(
    `${BASE_URL}/bookings`,
    route(async ({ request }) => {
      const user = currentUser(request);
      const body = await readBody(request);
      const details: ErrorDetail[] = [];
      const slotId = body.slot_id;
      if (slotId === undefined) {
        details.push({ loc: ["body", "slot_id"], msg: "Field required" });
      } else if (typeof slotId !== "number" || !Number.isInteger(slotId)) {
        details.push({ loc: ["body", "slot_id"], msg: "Input should be a valid integer" });
      }
      rejectExtraKeys(body, ["slot_id"], details);
      fail(details);
      return HttpResponse.json(db.createBooking(user, slotId as number), { status: 201 });
    }),
  ),

  // cancelBooking
  http.delete(
    `${BASE_URL}/bookings/:booking_id`,
    route(({ request, params }) => {
      const user = currentUser(request);
      const details: ErrorDetail[] = [];
      const bookingId = intParam(params.booking_id, ["path", "booking_id"], details);
      fail(details);
      return HttpResponse.json(db.cancelBooking(user, bookingId!));
    }),
  ),

  // listMyBookings
  http.get(
    `${BASE_URL}/me/bookings`,
    route(({ request }) => HttpResponse.json(db.listMyBookings(currentUser(request)))),
  ),

  // adminListBookings
  http.get(
    `${BASE_URL}/admin/bookings`,
    route(({ request }) => {
      currentAdmin(request);
      const query = new URL(request.url).searchParams;
      const details: ErrorDetail[] = [];
      const labId = intParam(query.get("lab_id"), ["query", "lab_id"], details);
      if (labId !== null) db.assertActiveLab(labId); // 404 before the date is validated
      const date = dateParam(query.get("date"), ["query", "date"], details);
      fail(details);
      return HttpResponse.json(db.adminListBookings(labId!, date!));
    }),
  ),

  // adminCreateClosure
  http.post(
    `${BASE_URL}/admin/labs/:lab_id/closures`,
    route(async ({ request, params }) => {
      currentAdmin(request);
      const pathDetails: ErrorDetail[] = [];
      const labId = intParam(params.lab_id, ["path", "lab_id"], pathDetails);
      fail(pathDetails);
      db.assertActiveLab(labId!); // 404 before the body is validated

      const body = await readBody(request);
      const details: ErrorDetail[] = [];
      const date = dateParam(
        typeof body.date === "string" || body.date === undefined ? (body.date as string | undefined) : "",
        ["body", "date"],
        details,
      );
      rejectExtraKeys(body, ["date"], details);
      fail(details);
      return HttpResponse.json(db.createClosure(labId!, date!), { status: 201 });
    }),
  ),
];

// Any other path under the backend URL is an unknown route (404 `not_found`). Only added
// for an absolute base URL: with a relative one it would also catch the app's own files.
if (/^https?:\/\//.test(BASE_URL)) {
  handlers.push(
    http.all(
      `${BASE_URL}/*`,
      route(() => {
        throw new MockHttpError(404, "not_found", "Not found.");
      }),
    ),
  );
}

export { handlers };
