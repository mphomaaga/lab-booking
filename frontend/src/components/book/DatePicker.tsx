import { useId } from "react";
import { formatDate } from "../../lib/time";

interface DatePickerProps {
  /** The bookable dates, today first (`bookingWindowDates`). */
  dates: string[];
  value: string;
  disabled?: boolean;
  onChange: (date: string) => void;
}

export function DatePicker({ dates, value, disabled = false, onChange }: DatePickerProps) {
  const id = useId();
  return (
    <div className="book-field">
      <label htmlFor={id}>Date</label>
      <select id={id} value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)}>
        {dates.map((date, index) => (
          <option key={date} value={date}>
            {index === 0 ? `Today, ${formatDate(date)}` : formatDate(date)}
          </option>
        ))}
      </select>
    </div>
  );
}
