import { useState } from "react";
import { Button } from "./Button";
import { cn } from "../../utils/cn";

/**
 * Preset pills plus an optional "Custom" numeric entry.
 *
 * Lifted out of CreateQuizPage so EDIT QUIZ can offer the *identical* timer
 * control - create and edit must never drift onto different value sets.
 */
export interface SelectWithCustomProps {
  value: number;
  onChange: (v: string) => void;
  presets: readonly number[];
  /** Suffix shown on each pill / inside the custom box, e.g. "sec" | "pts". */
  unit: string;
  /** Inclusive bounds for the custom box (backend rejects anything outside). */
  min?: number;
  max?: number;
}

export function SelectWithCustom({
  value,
  onChange,
  presets,
  unit,
  min = 1,
  max = unit === "sec" ? 300 : 100000,
}: SelectWithCustomProps) {
  const [isCustom, setIsCustom] = useState(false);
  const [customValue, setCustomValue] = useState("");

  if (isCustom) {
    return (
      <div className="flex flex-wrap gap-2">
        <input
          type="number"
          value={customValue || value}
          onChange={(e) => {
            const v = e.target.value;
            setCustomValue(v);
            onChange(v);
          }}
          min={min}
          max={max}
          className="glass-input flex-1 min-w-[8rem] px-4 py-3 rounded-xl text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
        />
        <span className="flex items-center px-3 text-gray-400">{unit}</span>
        <Button variant="ghost" size="sm" onClick={() => setIsCustom(false)}>
          Use Preset
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-2">
      {presets.map((p) => (
        <button
          key={p}
          type="button"
          onClick={() => {
            setIsCustom(false);
            onChange(String(p));
          }}
          className={cn(
            "px-3.5 py-2 rounded-xl text-sm font-medium border-2 transition-all duration-200",
            value === p
              ? "border-transparent bg-gradient-to-r from-purple-600 to-fuchsia-600 text-white shadow-playoot-sm"
              : "border-white/10 bg-white/5 text-gray-300 hover:border-white/25 hover:bg-white/10"
          )}
        >
          {p}
          {unit}
        </button>
      ))}
      <Button variant="outline" size="sm" onClick={() => setIsCustom(true)}>
        Custom {unit}
      </Button>
    </div>
  );
}

export default SelectWithCustom;
