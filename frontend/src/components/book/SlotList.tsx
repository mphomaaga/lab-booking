import type { Slot } from "../../api/types";
import { formatTime } from "../../lib/time";

interface SlotListProps {
  slots: Slot[];
  /** Slot being booked right now, if any. */
  submittingSlotId: number | null;
  onBook: (slot: Slot) => void;
}

function seatsText(slot: Slot): string {
  const noun = slot.seats === 1 ? "seat" : "seats";
  return `${slot.free_seats} of ${slot.seats} ${noun} free`;
}

export function SlotList({ slots, submittingSlotId, onBook }: SlotListProps) {
  // While any booking request is in flight every button is disabled, so a slot can't be
  // submitted twice and two requests can't race each other.
  const busy = submittingSlotId !== null;

  return (
    <ul className="slot-list">
      {slots.map((slot) => {
        const start = formatTime(slot.start_time);
        const end = formatTime(slot.end_time);
        return (
          <li key={slot.id} className={slot.bookable ? "slot-card" : "slot-card slot-card-unavailable"}>
            <span className="slot-time">
              {start} - {end}
            </span>
            <span className="slot-seats">{seatsText(slot)}</span>
            {slot.bookable ? (
              <button
                type="button"
                className="btn btn-primary"
                disabled={busy}
                aria-label={`Book ${start} to ${end}`}
                onClick={() => onBook(slot)}
              >
                {submittingSlotId === slot.id ? "Booking..." : "Book"}
              </button>
            ) : (
              <button type="button" className="btn" disabled>
                {slot.free_seats === 0 ? "Full" : "Started"}
              </button>
            )}
          </li>
        );
      })}
    </ul>
  );
}
