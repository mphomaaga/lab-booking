import type { Booking } from "../../api/types";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { formatInstantDate, formatTime } from "../../lib/time";

interface CancelBookingDialogProps {
  /** The booking the user is about to cancel, or null when the dialog is closed. */
  booking: Booking | null;
  busy: boolean;
  onConfirm: () => void;
  onDismiss: () => void;
}

/** Names the exact booking, and labels the buttons so neither can be mistaken for the other. */
export function CancelBookingDialog({ booking, busy, onConfirm, onDismiss }: CancelBookingDialogProps) {
  return (
    <ConfirmDialog
      open={booking !== null}
      title="Cancel this booking?"
      confirmLabel={busy ? "Cancelling..." : "Yes, cancel booking"}
      cancelLabel="Keep booking"
      danger
      busy={busy}
      onConfirm={onConfirm}
      onCancel={onDismiss}
    >
      {booking && (
        <>
          <p className="dialog-booking">
            <strong>{booking.lab.name}</strong>
            <br />
            {formatInstantDate(booking.slot.start_time)}, {formatTime(booking.slot.start_time)} to{" "}
            {formatTime(booking.slot.end_time)}
          </p>
          <p>The slot is released for other students.</p>
        </>
      )}
    </ConfirmDialog>
  );
}
