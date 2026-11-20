import { ApiError, errorMessage } from "../../api/errors";
import type { ErrorCode } from "../../api/types";

// A message a student can act on for each error `createBooking` documents (docs/api.yaml,
// POST /bookings). Anything else falls back to the message the server sent.
const BOOKING_MESSAGES: Partial<Record<ErrorCode, string>> = {
  slot_not_found: "That slot is no longer available. The list below has been refreshed.",
  slot_in_past: "That slot has already started, so it can't be booked any more.",
  outside_booking_window: "You can only book today and the next 6 days.",
  lab_closed: "This lab is closed on that date, so it can't be booked.",
  already_booked: "You have already booked this slot. You can see it under My bookings.",
  overlapping_booking:
    "You already have a booking at this time in another lab. Cancel that booking under My bookings first if you want this one instead.",
  daily_limit_reached:
    "You already have 2 bookings on this day, which is the most you can have. Cancel one under My bookings to book another.",
  slot_full: "Someone else just took the last seat in that slot. Pick another slot.",
  validation_error: "That booking request wasn't valid. Please try again.",
};

/** The message to show a student after `createBooking` fails. */
export function bookingErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return BOOKING_MESSAGES[error.code] ?? errorMessage(error);
  return errorMessage(error);
}

const LOAD_MESSAGES: Partial<Record<ErrorCode, string>> = {
  lab_not_found: "That lab is no longer available. Pick another lab.",
  date_out_of_window: "You can only view today and the next 6 days. The dates have been refreshed.",
  validation_error: "That date isn't valid. Pick one from the list.",
};

/** The message to show a student after `getLabSlots` fails. */
export function loadErrorMessage(error: unknown): string {
  if (error instanceof ApiError) return LOAD_MESSAGES[error.code] ?? errorMessage(error);
  return errorMessage(error);
}
