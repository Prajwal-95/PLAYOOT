import React, { forwardRef } from 'react';
import { cn } from "../../utils/cn";

interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: "default" | "primary" | "secondary" | "success" | "warning" | "error" | "brand" | "accent" | "outline";
  size?: "xs" | "sm" | "md" | "lg";
  dot?: boolean;
  icon?: React.ReactNode;
}

export const Badge = forwardRef<HTMLSpanElement, BadgeProps>(
  ({ className, variant = "default", size = "md", dot, icon, children, ...rest }, ref) => {
    const variants = {
      default: "bg-gray-700/50 text-gray-200 border border-gray-600",
      primary: "bg-purple-600/20 text-purple-300 border-purple-500/30",
      secondary: "bg-pink-600/20 text-pink-300 border-pink-500/30",
      success: "bg-emerald-600/20 text-emerald-300 border-emerald-500/30",
      warning: "bg-amber-600/20 text-amber-300 border-amber-500/30",
      error: "bg-red-600/20 text-red-300 border-red-500/30",
      brand: "bg-gradient-to-r from-purple-600 to-violet-600 text-white",
      accent: "bg-gradient-to-r from-cyan-500 to-blue-500 text-white",
      outline: "bg-transparent text-gray-300 border-gray-600",
    };

    const sizes = {
      xs: "px-2 py-0.5 text-xs gap-1",
      sm: "px-2.5 py-0.5 text-xs gap-1",
      md: "px-3 py-1 text-sm gap-1.5",
      lg: "px-4 py-1.5 text-base gap-2",
    };

    return (
      <span
        ref={ref}
        className={cn(
          "inline-flex items-center font-medium rounded-full border",
          variants[variant],
          sizes[size],
          className
        )}
        {...rest}
      >
        {dot && <span className="w-1.5 h-1.5 rounded-full bg-current animate-pulse" />}
        {icon}
        <span className="font-medium">{children}</span>
      </span>
    );
  }
);

Badge.displayName = "Badge";

export default Badge;