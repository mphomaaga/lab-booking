import type { Lab } from "../../api/types";

interface AdminFiltersProps {
  labs: Lab[];
  labId: number | null;
  /** The raw value of the date input; empty while the user is editing it. */
  date: string;
  onLabChange: (labId: number) => void;
  onDateChange: (date: string) => void;
}

/** Lab picker and date picker. The date picker allows any date (US-6, no window for admins). */
export function AdminFilters({ labs, labId, date, onLabChange, onDateChange }: AdminFiltersProps) {
  return (
    <div className="admin-filters">
      <div className="admin-field">
        <label htmlFor="admin-lab">Lab</label>
        <select
          id="admin-lab"
          value={labId ?? ""}
          onChange={(event) => onLabChange(Number(event.target.value))}
        >
          {labs.map((lab) => (
            <option key={lab.id} value={lab.id}>
              {lab.name}
            </option>
          ))}
        </select>
      </div>
      <div className="admin-field">
        <label htmlFor="admin-date">Date</label>
        <input
          id="admin-date"
          type="date"
          value={date}
          onChange={(event) => onDateChange(event.target.value)}
        />
      </div>
    </div>
  );
}
