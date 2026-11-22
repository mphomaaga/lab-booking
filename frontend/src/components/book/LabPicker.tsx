import { useId } from "react";
import type { Lab } from "../../api/types";

interface LabPickerProps {
  labs: Lab[];
  value: number | null;
  disabled?: boolean;
  onChange: (labId: number) => void;
}

export function LabPicker({ labs, value, disabled = false, onChange }: LabPickerProps) {
  const id = useId();
  return (
    <div className="book-field">
      <label htmlFor={id}>Lab</label>
      <select
        id={id}
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {labs.map((lab) => (
          <option key={lab.id} value={lab.id}>
            {lab.name} ({lab.seats} seats)
          </option>
        ))}
      </select>
    </div>
  );
}
