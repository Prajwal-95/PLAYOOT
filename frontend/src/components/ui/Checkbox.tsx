import React, { forwardRef } from 'react';
import { cn } from "../../utils/cn";
import { Check } from "lucide-react";

interface CheckboxProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  description?: string;
  indeterminate?: boolean;
}

export const Checkbox = forwardRef<HTMLInputElement, CheckboxProps>(
  ({ className, label, description, indeterminate, disabled, id, ...props }, ref) => {
    const checkboxId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="w-full">
        <div className="flex items-start gap-3">
          <div className="relative flex items-center justify-center flex-shrink-0">
            <input
              ref={ref}
              id={checkboxId}
              type="checkbox"
              className={cn(
                "sr-only peer",
                disabled && "pointer-events-none cursor-not-allowed"
              )}
              disabled={disabled}
              aria-describedby={props['aria-describedby']}
              {...props}
            />
            <div className={cn(
              "w-5 h-5 rounded-lg border-2 flex items-center justify-center transition-all duration-200",
              "bg-gray-800 border-gray-600",
              "peer-focus:ring-2 peer-focus:ring-purple-500 peer-focus:ring-offset-2 peer-focus:ring-offset-gray-900",
              "peer-checked:bg-gradient-to-r peer-checked:from-purple-600 peer-checked:to-violet-600 peer-checked:border-transparent",
              "peer-indeterminate:bg-purple-600 peer-indeterminate:border-purple-600",
              "hover:peer-checked:shadow-playoot-sm",
              disabled && "opacity-50 cursor-not-allowed",
              "peer-checked:hover:shadow-playoot-md",
              "rounded-lg"
            )}>
              {indeterminate ? (
                <div className="w-2.5 h-0.5 bg-white rounded" />
              ) : (
                <Check className="w-3.5 h-3.5 text-white" strokeWidth={3} />
              )}
            </div>
          </div>
          {(label || description) && (
            <div className="flex-1 min-w-0">
              {label && (
                <label 
                  htmlFor={checkboxId} 
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

Checkbox.displayName = "Checkbox";

export default Checkbox;