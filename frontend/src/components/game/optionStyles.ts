import { Circle, Diamond, Square, Triangle } from "lucide-react";
import type { LucideIcon } from "lucide-react";

/**
 * Kahoot's four signature option tiles, in wire order.
 *
 * The SAME array drives the host stage and the player stage, so option 0 is a
 * rose tile with a triangle on both screens, option 1 is a sky tile with a
 * circle, option 2 an amber tile with a square and option 3 an emerald tile
 * with a diamond.  Shapes come from lucide so they render identically
 * everywhere instead of relying on platform emoji/font glyphs.
 */
export interface OptionStyle {
  /** Kahoot signature tile colour, in wire order. */
  tile: string;
  /** Shape badge shown inside the tile. */
  badge: string;
  /** Response-bar colour used by the host reveal. */
  bar: string;
  /** Distinct shape icon - identical on host and player screens. */
  Shape: LucideIcon;
}

export const OPTION_STYLES: OptionStyle[] = [
  {
    tile: "bg-rose-600 hover:bg-rose-500",
    badge: "bg-rose-700/60 text-white",
    bar: "bg-rose-500",
    Shape: Triangle,
  },
  {
    tile: "bg-sky-600 hover:bg-sky-500",
    badge: "bg-sky-700/60 text-white",
    bar: "bg-sky-500",
    Shape: Circle,
  },
  {
    tile: "bg-amber-500 hover:bg-amber-400",
    badge: "bg-amber-600/70 text-white",
    bar: "bg-amber-400",
    Shape: Square,
  },
  {
    tile: "bg-emerald-600 hover:bg-emerald-500",
    badge: "bg-emerald-700/60 text-white",
    bar: "bg-emerald-500",
    Shape: Diamond,
  },
];
