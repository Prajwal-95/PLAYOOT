import React, { forwardRef } from 'react';
import { cn } from "../../utils/cn";

interface RadioProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  description?: string;
}

export const Radio = forwardRef<HTMLInputElement, RadioProps>(
  ({ className, label, description, disabled, id, ...props }, ref) => {
    const radioId = id || label?.toLowerCase().replace(/\s+/g, "-");

    return (
      <div className="w-full">
        <div className="flex items-start gap-3">
          <div className="relative flex items-center justify-center flex-shrink-0">
            <input
              ref={ref}
              id={radioId}
              type="radio"
              className={cn(
                "sr-only peer",
                disabled && "pointer-events-none cursor-not-allowed"
              )}
              disabled={disabled}
              aria-describedby={props['aria-describedby']}
              {...props}
            />
            <div className={cn(
              "w-5 h-5 rounded-full border-2 flex items-center justify-center transition-all duration-200",
              "bg-gray-800 border-gray-600",
              "peer-focus:ring-2 peer-focus:ring-purple-500 peer-focus:ring-offset-2 peer-focus:ring-offset-gray-900",
              "peer-checked:border-purple-500 peer-checked:bg-purple-600",
              "peer-checked:after:content-[''] peer-checked:after:w-2 peer-checked:after:h-2 peer-checked:after:rounded-full peer-checked:after:bg-white",
              "hover:peer-checked:shadow-playoot-sm",
              disabled && "opacity-50 cursor-not-allowed",
              "rounded-full"
            )}>
              <div className="w-2 h-2 rounded-full bg-white opacity-0 peer-checked:opacity-100 transition-opacity duration-200" />
            </div>
          </div>
          {(label || description) && (
            <div className="flex-1 min-w-0">
              {label && (
                <label 
                  htmlFor={radioId} 
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

Radio.displayName = "Radio";

export default Radio;