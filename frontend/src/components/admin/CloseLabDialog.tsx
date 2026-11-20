import { useEffect, useRef } from "react";
import { ConfirmDialog } from "../ui/ConfirmDialog";

interface CloseLabDialogProps {
  open: boolean;
  labName: string;
  /** Display date, for example "Thu, 19 Nov 2026". */
  dateText: string;
  /** Active bookings on the date that haven't started, counted from the list on screen. */
  affectedCount: number;
  busy: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * Focuses the dialog's first button (Cancel) once it opens. ConfirmDialog autofocuses its
 * confirm button, so without this a stray Enter would close the lab, which cancels
 * students' bookings. Remove once ConfirmDialog stops autofocusing the confirm action.
 */
function FocusCancel() {
  const ref = useRef<HTMLSpanElement>(null);
  useEffect(() => {
    ref.current?.closest('[role="dialog"]')?.querySelector("button")?.focus();
  }, []);
  return <span ref={ref} hidden />;
}

export function CloseLabDialog({
  open,
  labName,
  dateText,
  affectedCount,
  busy,
  onConfirm,
  onCancel,
}: CloseLabDialogProps) {
  return (
    <ConfirmDialog
      open={open}
      title="Close lab for this date?"
      confirmLabel="Close lab and cancel bookings"
      cancelLabel="Keep lab open"
      danger
      busy={busy}
      onConfirm={onConfirm}
      onCancel={onCancel}
    >
      <FocusCancel />
      <p>
        You are about to close <strong>{labName}</strong> on <strong>{dateText}</strong>.
      </p>
      <p>
        Every active booking that hasn&apos;t started yet will be cancelled, and the students
        will lose their places.{" "}
        {affectedCount > 0 ? (
          <strong>
            {affectedCount} {affectedCount === 1 ? "booking is" : "bookings are"} affected on the
            list you are looking at.
          </strong>
        ) : (
          <>No bookings on the list you are looking at are affected.</>
        )}
      </p>
      <p>
        <strong>This can&apos;t be undone.</strong> A closed lab can&apos;t be reopened.
      </p>
    </ConfirmDialog>
  );
}
