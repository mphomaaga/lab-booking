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

/**
 * Everything the close dialog describes and everything the close request uses, captured once
 * when the dialog opens. The dialog text, the request and the reload all read from this and
 * never from live state, so a lab or date change can't make them disagree.
 */
interface CloseSnapshot {
  labId: number;
  labName: string;
  date: string;
  affected: number;
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

  // Non-null while the close dialog is open. Set only by openConfirm; cleared on any lab or
  // date change, on cancel and when the request finishes.
  const [closeTarget, setCloseTarget] = useState<CloseSnapshot | null>(null);
  const [preparing, setPreparing] = useState(false); // refetching the day before the dialog opens
  const [closing, setClosing] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const [result, setResult] = useState<ClosureResult | null>(null);

  // Only the newest bookings request may update the screen.
  const requestId = useRef(0);

  const validDate = DATE_PATTERN.test(date);

  // The selection as currently shown, for checks made after an await.
  const labIdRef = useRef<number | null>(null);
  labIdRef.current = labId;
  const dateRef = useRef(date);
  dateRef.current = date;
  // Bumped on every lab or date change and every dialog open, so a slow day refetch that
  // belongs to an older selection can't open the dialog.
  const selectionVersion = useRef(0);

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
      if (next !== current) {
        // The selection is changing under us: any open or pending close dialog is stale.
        selectionVersion.current++;
        setCloseTarget(null);
        setPreparing(false);
      }
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
    // Whatever caused this change (picker, lab-gone switch), a dialog for the old selection
    // must not survive it.
    setCloseTarget(null);
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

  /**
   * Refetches the day, then opens the dialog with a snapshot taken from that fresh list, so
   * the booking count is current rather than whatever was loaded earlier. If the selection
   * changes while the refetch is in flight the result is discarded and no dialog opens.
   */
  const openConfirm = async () => {
    if (labId === null || !data || preparing || closing) return;
    const forLab = labId;
    const forDate = data.date;
    const version = ++selectionVersion.current;
    setActionError(null);
    setPreparing(true);
    try {
      const fresh = await adminListBookings(forLab, forDate);
      if (version !== selectionVersion.current) return; // selection moved on: discard
      setData(fresh);
      if (fresh.closed || fresh.date < todayLocal()) {
        setActionError("This lab can no longer be closed on that date.");
        return;
      }
      const now = Date.now();
      setCloseTarget({
        labId: forLab,
        labName: fresh.lab.name,
        date: fresh.date,
        affected: fresh.bookings.filter(
          (b) => b.status === "active" && new Date(b.slot.start_time).getTime() > now,
        ).length,
      });
    } catch (error) {
      if (version !== selectionVersion.current) return;
      setActionError(errorMessage(error));
      if (error instanceof ApiError && error.code === "lab_not_found") void refreshLabs();
    } finally {
      if (version === selectionVersion.current) setPreparing(false);
    }
  };

  /** Closes the lab described by the snapshot. Reads nothing from live state except to compare. */
  const closeLab = async (target: CloseSnapshot) => {
    setClosing(true);
    setActionError(null);
    let reload = false;
    let labMissing = false;
    let failure: string | null = null;
    try {
      const created: ClosureCreated = await adminCreateClosure(target.labId, target.date);
      setResult({
        labName: target.labName,
        date: created.date,
        cancelledCount: created.cancelled_booking_count,
      });
      reload = true;
    } catch (error) {
      failure = errorMessage(error);
      // closure_exists, closure_date_in_past, lab_not_found: show the message and reload.
      reload = error instanceof ApiError && RELOAD_CODES.has(error.code);
      labMissing = error instanceof ApiError && error.code === "lab_not_found";
    }
    setClosing(false);
    setCloseTarget(null);

    const sameSelection = () =>
      labIdRef.current === target.labId && dateRef.current === target.date;
    if (failure !== null) {
      // If the pickers moved on during the request, say which lab and date the error is for.
      setActionError(
        sameSelection()
          ? failure
          : `Closing ${target.labName} on ${formatDate(target.date)} failed: ${failure}`,
      );
    }
    if (!reload || !sameSelection()) return; // never paint the old lab or date over the pickers
    // If the lab is gone, refreshing the labs switches lab and the effect loads the new list.
    const selected = labMissing ? await refreshLabs() : target.labId;
    if (selected === target.labId && sameSelection()) {
      await fetchBookings(target.labId, target.date, false);
    }
  };

  const changeLab = (id: number) => {
    selectionVersion.current++;
    setCloseTarget(null);
    setPreparing(false);
    setResult(null);
    setActionError(null);
    setLabId(id);
  };

  const changeDate = (value: string) => {
    selectionVersion.current++;
    setCloseTarget(null);
    setPreparing(false);
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
                    onClick={() => void openConfirm()}
                    disabled={closing || loading || preparing}
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
            open={closeTarget !== null}
            labName={closeTarget?.labName ?? ""}
            dateText={closeTarget ? formatDate(closeTarget.date) : ""}
            affectedCount={closeTarget?.affected ?? 0}
            busy={closing}
            onConfirm={() => {
              if (closeTarget) void closeLab(closeTarget);
            }}
            onCancel={() => setCloseTarget(null)}
          />
        </>
      )}
    </div>
  );
}
