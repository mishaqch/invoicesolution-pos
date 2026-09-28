import { initials } from "@/lib/utils";
import type { RosterStaff } from "@/types";

interface Props {
  staff: RosterStaff;
  onSelect: (staff: RosterStaff) => void;
}

/** A roster name tile. Disabled when the staff member has no PIN set. */
export function StaffTile({ staff, onSelect }: Props) {
  const disabled = !staff.has_pin;
  return (
    <button
      type="button"
      className="staff-tile"
      disabled={disabled}
      onClick={() => onSelect(staff)}
      aria-label={`Sign in as ${staff.name}${disabled ? " (no PIN set)" : ""}`}
    >
      <span className="av" aria-hidden="true">
        {initials(staff.name)}
      </span>
      <span className="nm">{staff.name}</span>
      <span className="rl">{staff.role}</span>
      {disabled ? <span className="nopin">No PIN set</span> : null}
    </button>
  );
}
