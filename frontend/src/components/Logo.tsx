import { useId } from "react";
import { cn } from "../utils/cn";

interface LogoProps {
  /** Height/width of the square mark in pixels. */
  size?: number;
  /** Render the "PLAYOOT" wordmark next to the mark. */
  showWordmark?: boolean;
  /** Stack the wordmark under the mark instead of beside it. */
  stacked?: boolean;
  className?: string;
}

/**
 * PLAYOOT brand mark — a rounded-square gradient badge with a lightning bolt
 * and a sparkle, plus an optional frozen-glass wordmark.
 */
export function Logo({
  size = 40,
  showWordmark = true,
  stacked = false,
  className,
}: LogoProps) {
  const id = useId();
  const gradId = `playoot-grad-${id}`;
  const shineId = `playoot-shine-${id}`;

  return (
    <span
      className={cn(
        "inline-flex items-center",
        stacked ? "flex-col gap-2" : "gap-2.5",
        className
      )}
    >
      <svg
        width={size}
        height={size}
        viewBox="0 0 48 48"
        className="logo-mark flex-shrink-0"
        role="img"
        aria-label="PLAYOOT"
      >
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#a855f7" />
            <stop offset="52%" stopColor="#d946ef" />
            <stop offset="100%" stopColor="#06b6d4" />
          </linearGradient>
          <linearGradient id={shineId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#ffffff" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Badge */}
        <rect x="2" y="2" width="44" height="44" rx="14" fill={`url(#${gradId})`} />
        <rect
          x="2"
          y="2"
          width="44"
          height="22"
          rx="14"
          fill={`url(#${shineId})`}
        />

        {/* Lightning bolt */}
        <path
          d="M27.5 9 L15 26.5 h7.6 L20.5 39 L34 21 h-7.4 z"
          fill="#ffffff"
          stroke="#ffffff"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />

        {/* Sparkle */}
        <path
          d="M37 13 l1.1 2.6 2.6 1.1 -2.6 1.1 -1.1 2.6 -1.1 -2.6 -2.6 -1.1 2.6 -1.1 z"
          fill="#fde68a"
        />
      </svg>

      {showWordmark && (
        <span
          className={cn(
            "font-display font-bold tracking-tight leading-none",
            stacked && "text-center"
          )}
        >
          <span className="bg-gradient-to-r from-purple-300 via-pink-300 to-cyan-300 bg-clip-text text-transparent">
            PLAYOOT
          </span>
        </span>
      )}
    </span>
  );
}

export default Logo;
