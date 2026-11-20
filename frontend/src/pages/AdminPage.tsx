// Admin bookings screen (US-6, US-7): every booking for a lab and date, and a button to
// close the lab for that date. Reaching /admin is guarded by RequireAdmin in the shell.
import { useCallback, useEffect, useRef, useState } from "react";
import { adminCreateClosure, adminListBookings, errorMessage, listLabs } from "../api/client";
import { ApiError } from "../api/errors";
import type { AdminDayBookings, ClosureCreated, Lab } from "../api/types";
import { AdminBookingList } from "../components/admin/AdminBookingList";
import { AdminFilters } from "../components/admin/AdminFilters";
import { CloseLabDialog } from "../components/admin/CloseLabDialog";
import "../components/admin/admin.css";
import { ErrorMessage } from "../components/ui/ErrorMessage";
import { LoadingMessage } from "../components/ui/LoadingMessage";
import { formatDate, todayLocal } from "../lib/time";

const DATE_PATTERN = /^\d{4}-\d{2}-\d{2}$/;

/** After these the screen's data may be out of date, so it reloads (spec: closure errors). */
const RELOAD_CODES = new Set(["closure_exists", "closure_date_in_past", "lab_not_found"]);

interface ClosureResult {
  labName: string;
  date: string;
  cancelledCount: number;
}

function resultText({ labName, date, cancelledCount }: ClosureResult): string {
  const closed = `${labName} is now closed on ${formatDate(date)}.`;
  if (cancelledCount === 0) return `${closed} No bookings needed cancelling.`;
  const noun = cancelledCount === 1 ? "booking was" : "bookings were";
  return `${closed} ${cancelledCount} ${noun} cancelled.`;
}

export function AdminPage() {
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [labsError, setLabsError] = useState<string | null>(null);
  const [labId, setLabId] = useState<number | null>(null);
  const [date, setDate] = useState<string>(() => todayLocal());

  const [data, setData] = useState<AdminDayBookings | null>(null);
  const [loading, setLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [confirmOpen, setConfirmOpen] = useState(false);
  const [confirmAffected, setConfirmAffected] = useState(0);
  const [closing, setClosing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<ClosureResult | null>(null);

  // Only the newest bookings request may update the screen.
  const requestId = useRef(0);

  const validDate = DATE_PATTERN.test(date);

  const labIdRef = useRef<number | null>(null);
  labIdRef.current = labId;

  /** Reloads the lab list. Returns the id of the lab that is selected afterwards. */
  const refreshLabs = useCallback(async (): Promise<number | null> => {
    try {
      const list = await listLabs();
      setLabs(list);
      setLabsError(null);
      const current = labIdRef.current;
      if (current !== null && list.some((lab) => lab.id === current)) return current;
      // The lab is gone (or none was selected yet): fall back to the first one.
      const next = list[0]?.id ?? null;
      setLabId(next);
      if (current !== null) {
        setActionError((prev) => prev ?? "That lab is no longer available. Showing another lab.");
      }
      return next;
    } catch (error) {
      setLabsError(errorMessage(error));
      return labIdRef.current;
    }
  }, []);

  useEffect(() => {
    void refreshLabs();
  }, [refreshLabs]);

  const fetchBookings = useCallback(
    async (forLab: number, forDate: string, clearFirst: boolean) => {
      const id = ++requestId.current;
      setLoading(true);
      setLoadError(null);
      if (clearFirst) setData(null);
      try {
        const next = await adminListBookings(forLab, forDate);
        if (id !== requestId.current) return;
        setData(next);
      } catch (error) {
        if (id !== requestId.current) return;
        setData(null);
        setLoadError(errorMessage(error));
        if (error instanceof ApiError && error.code === "lab_not_found") void refreshLabs();
      } finally {
        if (id === requestId.current) setLoading(false);
      }
    },
    [refreshLabs],
  );

  // A new lab or date: drop what was on screen and load the new list.
  useEffect(() => {
    if (labId === null || !validDate) {
      requestId.current++; // ignore any request still in flight
      setData(null);
      setLoading(false);
      setLoadError(null);
      return;
    }
    void fetchBookings(labId, date, true);
  }, [labId, date, validDate, fetchBookings]);

  const today = todayLocal();
  const canClose = data !== null && !data.closed && data.date >= today;
  const selectedLab = labs?.find((lab) => lab.id === labId) ?? null;

  const openConfirm = () => {
    if (!data) return;
    const now = Date.now();
    setConfirmAffected(
      data.bookings.filter((b) => b.status === "active" && new Date(b.slot.start_time).getTime() > now)
        .length,
    );
    setActionError(null);
    setConfirmOpen(true);
  };

  const closeLab = async () => {
    if (labId === null || !data) return;
    const { date: closeDate, lab } = data;
    setClosing(true);
    setActionError(null);
    let reload = false;
    let labMissing = false;
    try {
      const created: ClosureCreated = await adminCreateClosure(labId, closeDate);
      setResult({
        labName: lab.name,
        date: created.date,
        cancelledCount: created.cancelled_booking_count,
      });
      reload = true;
    } catch (error) {
      setActionError(errorMessage(error));
      // closure_exists, closure_date_in_past, lab_not_found: show the message and reload.
      reload = error instanceof ApiError && RELOAD_CODES.has(error.code);
      labMissing = error instanceof ApiError && error.code === "lab_not_found";
    }
    setClosing(false);
    setConfirmOpen(false);
    if (!reload) return;
    // If the lab is gone, refreshing the labs switches lab and the effect loads the new list.
    const selected = labMissing ? await refreshLabs() : labId;
    if (selected === labId) await fetchBookings(labId, closeDate, false);
  };

  const changeLab = (id: number) => {
    setResult(null);
    setActionError(null);
    setLabId(id);
  };

  const changeDate = (value: string) => {
    setResult(null);
    setActionError(null);
    setDate(value);
  };

  return (
    <div>
      <h1>Admin bookings</h1>

      <ErrorMessage message={labsError} />
      {labsError && labs === null && (
        <p>
          <button type="button" className="btn" onClick={() => void refreshLabs()}>
            Try again
          </button>
        </p>
      )}
      {labs === null && !labsError && <LoadingMessage text="Loading labs..." />}

      {labs !== null && labs.length === 0 && <p className="admin-empty">There are no active labs.</p>}

      {labs !== null && labs.length > 0 && (
        <>
          <AdminFilters
            labs={labs}
            labId={labId}
            date={date}
            onLabChange={changeLab}
            onDateChange={changeDate}
          />

          {!validDate && <p className="admin-empty">Choose a date to see its bookings.</p>}

          {result && (
            <div className="admin-notice admin-notice-success" role="status">
              {resultText(result)}
            </div>
          )}
          <ErrorMessage message={actionError} />
          <ErrorMessage message={loadError} />
          {loadError && labId !== null && validDate && (
            <p>
              <button type="button" className="btn" onClick={() => void fetchBookings(labId, date, true)}>
                Try again
              </button>
            </p>
          )}

          {validDate && loading && data === null && <LoadingMessage text="Loading bookings..." />}

          {data && (
            <section aria-label={`Bookings for ${data.lab.name} on ${formatDate(data.date)}`}>
              <h2>
                {data.lab.name}, {formatDate(data.date)}
              </h2>

              {data.closed && (
                <div className="admin-notice admin-notice-closed" role="status">
                  This lab is closed on {formatDate(data.date)}.
                </div>
              )}

              {canClose && (
                <div className="admin-actions">
                  <button
                    type="button"
                    className="btn btn-danger"
                    onClick={openConfirm}
                    disabled={closing || loading}
                  >
                    Close lab for this date
                  </button>
                </div>
              )}

              {data.bookings.length === 0 ? (
                <p className="admin-empty">
                  No bookings for {data.lab.name} on {formatDate(data.date)}.
                </p>
              ) : (
                <AdminBookingList bookings={data.bookings} />
              )}
            </section>
          )}

          <CloseLabDialog
            open={confirmOpen}
            labName={data?.lab.name ?? selectedLab?.name ?? ""}
            dateText={data ? formatDate(data.date) : ""}
            affectedCount={confirmAffected}
            busy={closing}
            onConfirm={() => void closeLab()}
            onCancel={() => setConfirmOpen(false)}
          />
        </>
      )}
    </div>
  );
}
