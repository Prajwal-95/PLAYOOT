import React, { forwardRef } from 'react';
import { cn } from "../../utils/cn";

interface CardProps extends React.HTMLAttributes<HTMLDivElement> {
  variant?: "default" | "outlined" | "elevated" | "glass" | "gradient";
  interactive?: boolean;
  padding?: "none" | "sm" | "md" | "lg";
}

export const Card = forwardRef<HTMLDivElement, CardProps>(
  ({ className, variant = "default", interactive, padding = "md", children, ...props }, ref) => {
    const variants = {
      default: "bg-gray-800/40 backdrop-blur-md border border-white/10",
      outlined: "glass-card",
      elevated: "bg-gray-800/70 backdrop-blur-md border border-white/10 shadow-playoot-md",
      glass: "glass-card",
      gradient: "bg-gradient-to-br from-purple-900/30 via-violet-900/20 to-indigo-900/25 backdrop-blur-xl border border-purple-500/25",
    };

    const paddings = {
      none: "",
      sm: "p-4",
      md: "p-6",
      lg: "p-8",
    };

    return (
      <div
        ref={ref}
        className={cn(
          "rounded-2xl",
          variants[variant],
          paddings[padding],
          interactive && "transition-all duration-200 hover:shadow-playoot-md hover:-translate-y-0.5 cursor-pointer",
          className
        )}
        {...props}
      >
        {children}
      </div>
    );
  }
);

Card.displayName = "Card";

export const CardHeader = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div ref={ref} className={cn("mb-4", className)} {...props}>
      {children}
    </div>
  )
);
CardHeader.displayName = "CardHeader";

export const CardContent = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div ref={ref} className={cn("", className)} {...props}>
      {children}
    </div>
  )
);
CardContent.displayName = "CardContent";

export const CardFooter = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div ref={ref} className={cn("mt-4 pt-4 border-t border-gray-700/50 flex items-center gap-3", className)} {...props}>
      {children}
    </div>
  )
);
CardFooter.displayName = "CardFooter";

export default Card;