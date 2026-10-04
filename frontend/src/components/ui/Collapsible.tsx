import React, { useState } from "react";
import { cn } from "../../utils/cn";

interface CollapsibleSectionProps {
  /** Section heading. */
  title: string;
  /** Optional one-line description shown under the title. */
  subtitle?: string;
  /** Emoji or node shown in the leading tile. */
  icon?: React.ReactNode;
  /** Small pill shown next to the title (e.g. current value). */
  badge?: React.ReactNode;
  /** Whether the section starts expanded. */
  defaultOpen?: boolean;
  /** Accent colour for the icon tile. */
  accent?: "purple" | "cyan" | "pink" | "amber" | "emerald";
  className?: string;
  children: React.ReactNode;
}

const ACCENTS: Record<NonNullable<CollapsibleSectionProps["accent"]>, string> = {
  purple: "from-purple-500/25 to-violet-500/25 text-purple-200",
  cyan: "from-cyan-500/25 to-blue-500/25 text-cyan-200",
  pink: "from-pink-500/25 to-fuchsia-500/25 text-pink-200",
  amber: "from-amber-500/25 to-orange-500/25 text-amber-200",
  emerald: "from-emerald-500/25 to-green-500/25 text-emerald-200",
};

/**
 * A frosted-glass panel whose body smoothly slides down/up when the header is
 * clicked. Uses the CSS grid-rows 0fr -> 1fr trick so it animates to any
 * content height without measuring the DOM.
 */
export function CollapsibleSection({
  title,
  subtitle,
  icon,
  badge,
  defaultOpen = false,
  accent = "purple",
  className,
  children,
}: CollapsibleSectionProps) {
  const [open, setOpen] = useState(defaultOpen);

  return (
    <div
      className={cn(
        "glass-card rounded-2xl overflow-hidden transition-colors duration-300",
        open ? "border-purple-500/30" : "hover:border-white/20",
        className
      )}
    >
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="w-full flex items-center gap-4 px-5 py-4 text-left focus:outline-none focus-visible:ring-2 focus-visible:ring-purple-500 focus-visible:ring-inset"
      >
        {icon && (
          <span
            className={cn(
              "flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-xl bg-gradient-to-br text-xl shadow-inner",
              ACCENTS[accent]
            )}
          >
            {icon}
          </span>
        )}

        <span className="flex-1 min-w-0">
          <span className="flex items-center gap-2 flex-wrap">
            <span className="font-semibold text-white">{title}</span>
            {badge}
          </span>
          {subtitle && (
            <span className="block text-xs text-gray-400 mt-0.5">{subtitle}</span>
          )}
        </span>

        <span
          className={cn(
            "flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-full bg-white/5 text-gray-400 transition-transform duration-300",
            open && "rotate-180 text-purple-300"
          )}
          aria-hidden="true"
        >
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="currentColor">
            <path
              fillRule="evenodd"
              d="M5.23 7.21a.75.75 0 011.06.02L10 11.17l3.71-3.94a.75.75 0 111.08 1.04l-4.25 4.5a.75.75 0 01-1.08 0l-4.25-4.5a.75.75 0 01.02-1.06z"
              clipRule="evenodd"
            />
          </svg>
        </span>
      </button>

      <div className={cn("collapse-grid", open && "open")}>
        <div className="collapse-inner">
          <div className="px-5 pb-5 pt-1">{children}</div>
        </div>
      </div>
    </div>
  );
}

export default CollapsibleSection;
