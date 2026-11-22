import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, createBooking, getLabSlots, listLabs } from "../api/client";
import type { DaySlots, Lab, Slot } from "../api/types";
import { DatePicker } from "../components/book/DatePicker";
import { LabPicker } from "../components/book/LabPicker";
import { SlotList } from "../components/book/SlotList";
import { bookingErrorMessage, loadErrorMessage } from "../components/book/bookingErrors";
import "../components/book/book.css";
import { ErrorMessage } from "../components/ui/ErrorMessage";
import { LoadingMessage } from "../components/ui/LoadingMessage";
import { bookingWindowDates, formatDate, formatTime, todayLocal } from "../lib/time";

type Notice = { kind: "success" | "error"; text: string };

export function BookPage() {
  const [labs, setLabs] = useState<Lab[] | null>(null);
  const [labsError, setLabsError] = useState<string | null>(null);
  const [labsAttempt, setLabsAttempt] = useState(0);

  const [labId, setLabId] = useState<number | null>(null);
  const [dates, setDates] = useState<string[]>(() => bookingWindowDates());
  const [date, setDate] = useState<string>(() => todayLocal());

  const [day, setDay] = useState<DaySlots | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [submittingSlotId, setSubmittingSlotId] = useState<number | null>(null);

  // Synchronous guard: state updates are async, so two quick taps could both pass a check
  // on `submittingSlotId`. The ref closes that gap.
  const submitting = useRef(false);
  // Only the latest slots request may update the screen.
  const loadSeq = useRef(0);

  // Labs (US-2).
  useEffect(() => {
    let cancelled = false;
    setLabsError(null);
    listLabs()
      .then((result) => {
        if (cancelled) return;
        setLabs(result);
        setLabId((current) => current ?? result[0]?.id ?? null);
      })
      .catch((error: unknown) => {
        if (!cancelled) setLabsError(loadErrorMessage(error));
      });
    return () => {
      cancelled = true;
    };
  }, [labsAttempt]);

  const loadSlots = useCallback(async (lab: number, forDate: string): Promise<void> => {
    const seq = ++loadSeq.current;
    try {
      const result = await getLabSlots(lab, forDate);
      if (seq !== loadSeq.current) return;
      setDay(result);
      setLoadError(null);
    } catch (error) {
      if (seq !== loadSeq.current) return;
      setLoadError(loadErrorMessage(error));
      if (error instanceof ApiError && error.code === "date_out_of_window") {
        // The page was left open past midnight: the window has moved on.
        setDates(bookingWindowDates());
        setDate(todayLocal());
        setDay(null);
      }
    }
  }, []);

  // Slots for the chosen lab and date.
  useEffect(() => {
    if (labId === null) return;
    void loadSlots(labId, date);
    return () => {
      loadSeq.current++;
    };
  }, [labId, date, loadSlots]);

  function chooseLab(id: number) {
    setLabId(id);
    setDay(null);
    setLoadError(null);
    setNotice(null);
  }

  function chooseDate(next: string) {
    setDate(next);
    setDay(null);
    setLoadError(null);
    setNotice(null);
  }

  async function book(slot: Slot) {
    if (submitting.current || labId === null) return;
    submitting.current = true;
    setSubmittingSlotId(slot.id);
    setNotice(null);
    const labName = day?.lab.name ?? labs?.find((l) => l.id === labId)?.name ?? "the lab";
    try {
      await createBooking(slot.id);
      setNotice({
        kind: "success",
        text: `Booked: ${labName}, ${formatDate(date)}, ${formatTime(slot.start_time)} to ${formatTime(slot.end_time)}.`,
      });
    } catch (error) {
      setNotice({ kind: "error", text: bookingErrorMessage(error) });
    }
    // Success or failure, show the current seat counts (rules 5.6, 5.7, 5.8).
    await loadSlots(labId, date);
    submitting.current = false;
    setSubmittingSlotId(null);
  }

  const submittingNow = submittingSlotId !== null;

  let body;
  if (labsError) {
    body = (
      <>
        <ErrorMessage message={labsError} />
        <button type="button" className="btn" onClick={() => setLabsAttempt((n) => n + 1)}>
          Try again
        </button>
      </>
    );
  } else if (labs === null) {
    body = <LoadingMessage text="Loading labs..." />;
  } else if (labs.length === 0) {
    body = <p className="book-info">There are no labs to book right now.</p>;
  } else {
    body = (
      <>
        <div className="book-pickers">
          <LabPicker labs={labs} value={labId} disabled={submittingNow} onChange={chooseLab} />
          <DatePicker dates={dates} value={date} disabled={submittingNow} onChange={chooseDate} />
        </div>

        {notice?.kind === "success" && (
          <div className="book-notice" role="status">
            {notice.text}
          </div>
        )}
        {notice?.kind === "error" && <ErrorMessage message={notice.text} />}
        <ErrorMessage message={loadError} />

        {day === null ? (
          !loadError && <LoadingMessage text="Loading slots..." />
        ) : day.day_status === "weekend" ? (
          <p className="book-info book-info-closed">Labs are closed at weekends. Pick a weekday.</p>
        ) : day.day_status === "closed" ? (
          <p className="book-info book-info-closed">{day.lab.name} is closed on this date. Pick another date or lab.</p>
        ) : (
          <SlotList slots={day.slots} submittingSlotId={submittingSlotId} onBook={(slot) => void book(slot)} />
        )}
      </>
    );
  }

  return (
    <div>
      <h1>Book a slot</h1>
      {body}
    </div>
  );
}
