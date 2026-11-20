import { useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { cancelBooking, errorMessage, listMyBookings } from "../api/client";
import type { Booking } from "../api/types";
import { ErrorMessage } from "../components/ui/ErrorMessage";
import { LoadingMessage } from "../components/ui/LoadingMessage";
import { BookingItem } from "../components/my-bookings/BookingItem";
import { CancelBookingDialog } from "../components/my-bookings/CancelBookingDialog";
import "../components/my-bookings/my-bookings.css";

export function MyBookingsPage() {
  // null means "not loaded": first load, or the last load failed. A failed load never leaves old rows.
  const [bookings, setBookings] = useState<Booking[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState<Booking | null>(null);
  const [cancelling, setCancelling] = useState(false);

  const mounted = useRef(true);
  const latestLoad = useRef(0);

  const load = useCallback(async () => {
    const id = ++latestLoad.current;
    setLoading(true);
    try {
      const result = await listMyBookings();
      if (!mounted.current || id !== latestLoad.current) return;
      setBookings(result);
      setLoadError(null);
    } catch (error) {
      if (!mounted.current || id !== latestLoad.current) return;
      setBookings(null);
      setLoadError(errorMessage(error));
    } finally {
      if (mounted.current && id === latestLoad.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    mounted.current = true;
    void load();
    return () => {
      mounted.current = false;
    };
  }, [load]);

  const confirmCancel = useCallback(async () => {
    if (!pending || cancelling) return;
    setCancelling(true);
    setActionError(null);
    try {
      await cancelBooking(pending.id);
    } catch (error) {
      // booking_already_started, booking_already_cancelled, not_your_booking, booking_not_found:
      // show the contract's message, then reload so the list matches the server.
      if (mounted.current) setActionError(errorMessage(error));
    }
    if (!mounted.current) return;
    setPending(null);
    setCancelling(false);
    await load();
  }, [pending, cancelling, load]);

  const dismiss = useCallback(() => {
    if (!cancelling) setPending(null);
  }, [cancelling]);

  return (
    <section aria-labelledby="my-bookings-heading">
      <h1 id="my-bookings-heading">My bookings</h1>

      <ErrorMessage message={actionError} />
      <ErrorMessage message={loadError} />

      {loading && bookings === null && <LoadingMessage text="Loading your bookings..." />}

      {loadError !== null && !loading && (
        <button type="button" className="btn" onClick={() => void load()}>
          Try again
        </button>
      )}

      {bookings !== null && bookings.length === 0 && (
        <div className="empty-state">
          <p>You have no upcoming bookings.</p>
          <Link to="/book" className="btn">
            Book a slot
          </Link>
        </div>
      )}

      {bookings !== null && bookings.length > 0 && (
        <ul className="booking-list" aria-busy={loading}>
          {bookings.map((booking) => (
            <BookingItem
              key={booking.id}
              booking={booking}
              disabled={cancelling || loading}
              onCancel={(b) => {
                setActionError(null);
                setPending(b);
              }}
            />
          ))}
        </ul>
      )}

      <CancelBookingDialog
        booking={pending}
        busy={cancelling}
        onConfirm={() => void confirmCancel()}
        onDismiss={dismiss}
      />
    </section>
  );
}
