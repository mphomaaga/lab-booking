import type { Booking } from "../../api/types";
import { formatInstantDate, formatTime } from "../../lib/time";

interface BookingItemProps {
  booking: Booking;
  /** Disables the Cancel button while any cancellation is running. */
  disabled: boolean;
  onCancel: (booking: Booking) => void;
}

/** One booking: lab, local date, local start-end, a status label and (when allowed) Cancel. */
export function BookingItem({ booking, disabled, onCancel }: BookingItemProps) {
  const cancelled = booking.status === "cancelled";
  const date = formatInstantDate(booking.slot.start_time);
  const start = formatTime(booking.slot.start_time);
  const end = formatTime(booking.slot.end_time);

  return (
    <li className={cancelled ? "booking-item booking-item-cancelled" : "booking-item"}>
      <div className="booking-info">
        <p className="booking-lab">{booking.lab.name}</p>
        <p className="booking-time">
          <span className="booking-date">{date}</span>{" "}
          <span>
            {start} to {end}
          </span>
        </p>
        <p>
          <span className={cancelled ? "booking-badge badge-cancelled" : "booking-badge badge-active"}>
            {cancelled ? "Cancelled" : "Active"}
          </span>
        </p>
      </div>
      {booking.cancellable && (
        <button
          type="button"
          className="btn booking-cancel"
          disabled={disabled}
          aria-label={`Cancel booking: ${booking.lab.name}, ${date}, ${start} to ${end}`}
          onClick={() => onCancel(booking)}
        >
          Cancel
        </button>
      )}
    </li>
  );
}
