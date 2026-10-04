import React, { forwardRef } from 'react';
import { cn } from "../../utils/cn";

interface SwitchProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, "size"> {
  label?: string;
  description?: string;
  size?: "sm" | "md" | "lg";
}

export const Switch = forwardRef<HTMLInputElement, SwitchProps>(
  ({ className, label, description, disabled, size = "md", id, ...props }, ref) => {
    const switchId = id || label?.toLowerCase().replace(/\s+/g, "-");

    const sizes = {
      sm: "w-8 h-5",
      md: "w-11 h-6",
      lg: "w-14 h-7",
    };

    const thumbSizes = {
      sm: "w-4 h-4",
      md: "w-5 h-5",
      lg: "w-6 h-6",
    };

    const thumbTranslates = {
      sm: "translate-x-4",
      md: "translate-x-5",
      lg: "translate-x-7",
    };

    return (
      <div className="w-full">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center flex-shrink-0">
            <input
              ref={ref}
              id={switchId}
              type="checkbox"
              role="switch"
              className={cn(
                "sr-only peer",
                disabled && "pointer-events-none cursor-not-allowed"
              )}
              disabled={disabled}
              aria-describedby={props['aria-describedby']}
              {...props}
            />
            <div className={cn(
              "relative rounded-full bg-gray-700 border-2 border-gray-600 transition-all duration-200",
              "peer-focus:ring-2 peer-focus:ring-purple-500 peer-focus:ring-offset-2 peer-focus:ring-offset-gray-900",
              "peer-checked:bg-gradient-to-r peer-checked:from-purple-600 peer-checked:to-violet-600 peer-checked:border-transparent",
              "peer-checked:shadow-playoot-sm",
              "hover:peer-checked:shadow-playoot-md",
              disabled && "opacity-50 cursor-not-allowed",
              sizes[size],
              "flex items-center"
            )}>
              <div className={cn(
                "absolute top-0.5 left-0.5 bg-white rounded-full transition-transform duration-200 ease-spring",
                "shadow-lg",
                "peer-checked:translate-x-full",
                thumbSizes[size],
                thumbTranslates[size]
              )} />
            </div>
          </div>
          {(label || description) && (
            <div className="flex-1 min-w-0">
              {label && (
                <label 
                  htmlFor={switchId} 
                  className={cn(
                    "font-medium text-white cursor-pointer select-none",
                    disabled && "opacity-50 cursor-not-allowed"
                  )}
                >
                  {label}
                </label>
              )}
              {description && (
                <p className="mt-0.5 text-sm text-gray-500">{description}</p>
              )}
            </div>
          )}
        </div>
      </div>
    );
  }
);

Switch.displayName = "Switch";

export default Switch;