import type { AdminBooking } from "../../api/types";
import { formatDateTime, formatTime } from "../../lib/time";

/**
 * Bookings for one lab and date. A table on wide screens; on narrow screens the CSS turns
 * every row into a stacked card (spec section 7). Status is always written out, never
 * shown by colour alone.
 */
export function AdminBookingList({ bookings }: { bookings: AdminBooking[] }) {
  return (
    <table className="admin-table">
      <thead>
        <tr>
          <th scope="col">Slot</th>
          <th scope="col">Student number</th>
          <th scope="col">Status</th>
          <th scope="col">Booked at</th>
        </tr>
      </thead>
      <tbody>
        {bookings.map((booking) => {
          const cancelled = booking.status === "cancelled";
          return (
            <tr key={booking.id} className={cancelled ? "admin-row-cancelled" : undefined}>
              <td data-label="Slot">
                <span className="admin-time">{formatTime(booking.slot.start_time)}</span>
              </td>
              <td data-label="Student number">{booking.user.student_number}</td>
              <td data-label="Status">
                <span>
                  <span className={`admin-status admin-status-${booking.status}`}>
                    {cancelled ? "Cancelled" : "Active"}
                  </span>
                  {cancelled && booking.cancelled_at && (
                    <span className="admin-sub">at {formatDateTime(booking.cancelled_at)}</span>
                  )}
                </span>
              </td>
              <td data-label="Booked at">{formatDateTime(booking.created_at)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
