import React, { forwardRef } from 'react';
import { cn } from "../../utils/cn";

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?:
    | "primary"
    | "secondary"
    | "outline"
    | "ghost"
    | "danger"
    | "brand"
    | "accent"
    | "success"
    | "sunset"
    | "ocean"
    | "candy"
    | "rainbow";
  size?: "xs" | "sm" | "md" | "lg" | "xl" | "icon";
  loading?: boolean;
  fullWidth?: boolean;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ 
    className, 
    variant = "primary", 
    size = "md", 
    loading, 
    disabled,
    fullWidth,
    leftIcon,
    rightIcon,
    children, 
    ...props 
  }, ref) => {
    const baseStyles = "btn-shine inline-flex items-center justify-center font-medium rounded-xl transition-all duration-200 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-gray-950 disabled:opacity-50 disabled:cursor-not-allowed relative overflow-hidden active:scale-[0.97]";

    const variants = {
      primary: "bg-gradient-to-r from-purple-600 to-violet-600 text-white hover:from-purple-500 hover:to-violet-500 focus:ring-purple-500 shadow-playoot-sm hover:shadow-playoot-md hover:-translate-y-0.5",
      secondary: "bg-gray-700/50 text-white hover:bg-gray-600/50 focus:ring-gray-500 border border-gray-600 backdrop-blur-sm",
      outline: "border-2 border-gray-600 text-gray-200 hover:bg-gray-800/50 hover:border-gray-500 focus:ring-gray-500",
      ghost: "text-gray-300 hover:bg-gray-800/50 focus:ring-gray-500",
      danger: "bg-gradient-to-r from-red-600 to-rose-600 text-white hover:from-red-500 hover:to-rose-500 focus:ring-red-500 shadow-red-600/25 hover:shadow-red-600/40 hover:-translate-y-0.5",
      brand: "bg-gradient-to-r from-purple-600 via-fuchsia-600 to-indigo-600 text-white hover:from-purple-500 hover:via-fuchsia-500 hover:to-indigo-500 focus:ring-purple-500 shadow-playoot-md hover:shadow-playoot-lg hover:-translate-y-0.5",
      accent: "bg-gradient-to-r from-cyan-500 to-blue-500 text-white hover:from-cyan-400 hover:to-blue-400 focus:ring-cyan-500 shadow-cyan-500/25 hover:shadow-cyan-500/40 hover:-translate-y-0.5",
      success: "bg-gradient-to-r from-emerald-500 to-green-600 text-white hover:from-emerald-400 hover:to-green-500 focus:ring-emerald-500 shadow-emerald-500/25 hover:shadow-emerald-500/40 hover:-translate-y-0.5",
      sunset: "bg-gradient-to-r from-amber-500 via-orange-500 to-pink-600 text-white hover:from-amber-400 hover:via-orange-400 hover:to-pink-500 focus:ring-orange-500 shadow-orange-500/25 hover:shadow-orange-500/40 hover:-translate-y-0.5",
      ocean: "bg-gradient-to-r from-sky-500 via-cyan-500 to-teal-500 text-white hover:from-sky-400 hover:via-cyan-400 hover:to-teal-400 focus:ring-sky-500 shadow-sky-500/25 hover:shadow-sky-500/40 hover:-translate-y-0.5",
      candy: "bg-gradient-to-r from-pink-500 via-fuchsia-500 to-purple-600 text-white hover:from-pink-400 hover:via-fuchsia-400 hover:to-purple-500 focus:ring-pink-500 shadow-pink-500/25 hover:shadow-pink-500/40 hover:-translate-y-0.5",
      rainbow:
        "bg-gradient-to-r from-fuchsia-600 via-purple-600 to-cyan-500 bg-[length:200%_auto] text-white hover:bg-[position:right_center] focus:ring-fuchsia-500 shadow-playoot-md hover:shadow-playoot-lg hover:-translate-y-0.5",
    };

    const sizes = {
      xs: "px-2.5 py-1 text-xs gap-1",
      sm: "px-3 py-1.5 text-sm gap-1.5",
      md: "px-4 py-2 text-sm gap-2",
      lg: "px-6 py-3 text-base gap-2",
      xl: "px-8 py-4 text-lg gap-3",
      icon: "p-2",
    };

    const loadingSpinner = (
      <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24" aria-hidden="true">
        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
      </svg>
    );

    return (
      <button
        ref={ref}
        className={cn(
          baseStyles,
          variants[variant],
          sizes[size],
          fullWidth && "w-full",
          className
        )}
        disabled={disabled || loading}
        aria-busy={loading}
        aria-disabled={disabled || loading}
        {...props}
      >
        {loading ? loadingSpinner : leftIcon}
        <span className={cn(loading && "sr-only")}>{children}</span>
        {!loading && rightIcon}
        {loading && !rightIcon && (
          <span className="sr-only">Loading...</span>
        )}
        {/* Ripple effect overlay */}
        {!loading && (
          <span className="absolute inset-0 bg-white/10 pointer-events-none opacity-0" aria-hidden="true" />
        )}
      </button>
    );
  }
);

Button.displayName = "Button";

export default Button;