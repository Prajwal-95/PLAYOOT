import { useEffect, useRef } from "react";
import { Check } from "lucide-react";
import { cn } from "../../utils/cn";

/**
 * A bounded, vertically scrollable single-choice list.
 *
 * Why this exists: the old control was a bare `<input type="number">` whose
 * clamp ran on every keystroke, so clearing the box snapped the value back to
 * the minimum and the user could never type a new one. Nothing showed which
 * values were legal.
 *
 * This version:
 *  - lists every supported value so the choice is self-documenting,
 *  - scrolls INSIDE a fixed-height box (`max-h-… overflow-y-auto`) instead of
 *    growing the page, so nothing pushes the form around and nothing overflows
 *    its container (it therefore cannot be clipped by an ancestor), and
 *  - marks the current value with `aria-selected` + a visible check.
 *
 * Accessibility: every row is a real `<button>`, so Tab/Enter/Space work for
 * free; Arrow/Home/End on the list move focus between rows. The selected row
 * is scrolled into view by adjusting the container's own `scrollTop`, which
 * can never scroll the page.
 */
export interface ScrollSelectProps {
  label: string;
  value: number;
  options: readonly number[];
  onChange: (value: number) => void;
  /** Suffix rendered after each value, e.g. "sec" or "options". */
  unit?: string;
  min?: number;
  max?: number;
  helperText?: string;
  id?: string;
}

export function ScrollSelect({
  label,
  value,
  options,
  onChange,
  unit,
  min,
  max,
  helperText,
  id,
}: ScrollSelectProps) {
  const listRef = useRef<HTMLDivElement | null>(null);
  const rowRefs = useRef<Record<number, HTMLButtonElement | null>>({});

  // Keep the current value visible inside the list - by writing scrollTop
  // directly rather than scrollIntoView(), so the page itself never moves.
  useEffect(() => {
    const container = listRef.current;
    const row = rowRefs.current[value];
    if (!container || !row) return;
    const top = row.offsetTop;
    const bottom = top + row.offsetHeight;
    if (top < container.scrollTop) {
      container.scrollTop = top;
    } else if (bottom > container.scrollTop + container.clientHeight) {
      container.scrollTop = bottom - container.clientHeight;
    }
  }, [value, options]);

  const handleKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const keys = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keys.includes(event.key)) return;

    const rows = Array.from(
      listRef.current?.querySelectorAll<HTMLButtonElement>("button") ?? []
    );
    if (rows.length === 0) return;

    const current = rows.indexOf(document.activeElement as HTMLButtonElement);
    const selected = Math.max(
      0,
      rows.findIndex((row) => row.dataset.value === String(value))
    );
    const from = current === -1 ? selected : current;

    let next = from;
    if (event.key === "ArrowDown") next = Math.min(from + 1, rows.length - 1);
    else if (event.key === "ArrowUp") next = Math.max(from - 1, 0);
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = rows.length - 1;

    event.preventDefault();
    rows[next]?.focus();
  };

  const listId = id ?? `scroll-select-${label.toLowerCase().replace(/\s+/g, "-")}`;

  return (
    <div className="w-full">
      <label
        htmlFor={listId}
        className="block text-sm font-medium text-gray-300 mb-1.5"
      >
        {label}
      </label>

      <div className="flex items-center justify-between gap-3 mb-2">
        <span className="text-xs text-gray-500">
          {min !== undefined && max !== undefined
            ? `Choose ${min}–${max}`
            : `${options.length} choices`}
        </span>
        <span
          data-testid="scroll-select-value"
          className="text-xs font-semibold px-2.5 py-1 rounded-full bg-purple-500/20 text-purple-200 border border-purple-400/30 tabular-nums"
        >
          {value}
          {unit ? ` ${unit}` : ""}
        </span>
      </div>

      <div
        id={listId}
        ref={listRef}
        role="listbox"
        aria-label={label}
        tabIndex={-1}
        onKeyDown={handleKeyDown}
        className={cn(
          // Bounded + scrollable: the list never grows past this height, so it
          // neither grows the page nor overflows (and cannot be clipped).
          "max-h-44 min-h-[7.5rem] overflow-y-auto overscroll-contain",
          "rounded-xl border border-white/10 bg-black/30 py-1",
          "focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
        )}
      >
        {options.map((option) => {
          const selected = option === value;
          return (
            <button
              key={option}
              type="button"
              role="option"
              data-value={option}
              aria-selected={selected}
              ref={(node) => {
                rowRefs.current[option] = node;
              }}
              onClick={() => onChange(option)}
              className={cn(
                "w-full flex items-center justify-between gap-3 px-4 py-2.5 text-left",
                "text-sm transition-colors",
                selected
                  ? "bg-purple-600/30 text-white font-semibold"
                  : "text-gray-300 hover:bg-white/10 hover:text-white"
              )}
            >
              <span className="flex items-baseline gap-1.5">
                <span className="tabular-nums text-base font-semibold">{option}</span>
                {unit && <span className="text-gray-400 text-xs">{unit}</span>}
              </span>
              <span className="w-5 flex justify-end">
                {selected && (
                  <Check
                    className="w-4 h-4 text-purple-300"
                    strokeWidth={3}
                    aria-hidden="true"
                  />
                )}
              </span>
            </button>
          );
        })}
      </div>

      {helperText && (
        <p className="mt-1.5 text-xs text-gray-500">{helperText}</p>
      )}
    </div>
  );
}

export default ScrollSelect;
