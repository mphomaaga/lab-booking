// Hand-written mirror of the schemas in docs/api.yaml. Keep names, fields and
// nullability identical to the contract.

export type ErrorCode =
  | "not_authenticated"
  | "invalid_credentials"
  | "admin_required"
  | "not_your_booking"
  | "lab_not_found"
  | "slot_not_found"
  | "booking_not_found"
  | "not_found"
  | "lab_closed"
  | "already_booked"
  | "overlapping_booking"
  | "daily_limit_reached"
  | "slot_full"
  | "booking_already_cancelled"
  | "booking_already_started"
  | "closure_exists"
  | "validation_error"
  | "date_out_of_window"
  | "slot_in_past"
  | "outside_booking_window"
  | "closure_date_in_past"
  | "internal_error";

export interface ErrorDetail {
  loc: (string | number)[];
  msg: string;
}

export interface Error {
  error: {
    code: ErrorCode;
    message: string;
    /** Only for `validation_error` */
    details?: ErrorDetail[];
  };
}

export interface LoginRequest {
  student_number: string;
  password: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  /** UTC instant the token stops working */
  expires_at: string;
  user: User;
}

export interface User {
  id: number;
  student_number: string;
  is_admin: boolean;
}

export interface UserRef {
  id: number;
  student_number: string;
}

export interface Lab {
  id: number;
  name: string;
  seats: number;
}

export interface LabRef {
  id: number;
  name: string;
}

export type DayStatus = "open" | "closed" | "weekend";

export interface Slot {
  id: number;
  /** UTC instant, ISO 8601 with Z */
  start_time: string;
  /** Always start_time + 1 hour */
  end_time: string;
  /** The lab's seat count */
  seats: number;
  free_seats: number;
  /** true when start_time > now and free_seats > 0 */
  bookable: boolean;
}

export interface DaySlots {
  lab: Lab;
  /** Calendar date in Africa/Johannesburg, YYYY-MM-DD */
  date: string;
  day_status: DayStatus;
  /** Ten slots when day_status is open, otherwise empty */
  slots: Slot[];
}

export interface SlotRef {
  id: number;
  start_time: string;
  end_time: string;
}

export type BookingStatus = "active" | "cancelled";

export interface CreateBookingRequest {
  slot_id: number;
}

export interface Booking {
  id: number;
  status: BookingStatus;
  created_at: string;
  cancelled_at: string | null;
  /** true when status is active and slot start_time > now */
  cancellable: boolean;
  lab: LabRef;
  slot: SlotRef;
}

export interface AdminBooking {
  id: number;
  status: BookingStatus;
  created_at: string;
  cancelled_at: string | null;
  slot: SlotRef;
  user: UserRef;
}

export interface AdminDayBookings {
  lab: Lab;
  /** Calendar date in Africa/Johannesburg, YYYY-MM-DD */
  date: string;
  /** true when the lab has a closure on this date */
  closed: boolean;
  bookings: AdminBooking[];
}

export interface CreateClosureRequest {
  /** Calendar date in Africa/Johannesburg, today or later */
  date: string;
}

export interface ClosureCreated {
  id: number;
  lab_id: number;
  date: string;
  created_at: string;
  /** How many active, not-yet-started bookings this closure cancelled */
  cancelled_booking_count: number;
}
