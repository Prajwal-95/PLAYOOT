import React, { forwardRef } from 'react';
import { cn } from "../../utils/cn";

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
  hint?: string;
  leftIcon?: React.ReactNode;
  rightIcon?: React.ReactNode;
  leftAddon?: string;
  rightAddon?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, error, helperText, hint, leftIcon, rightIcon, leftAddon, rightAddon, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s+/g, "-");
    const hasError = !!error;
    const hasLeftAddon = !!leftAddon;
    const hasRightAddon = !!rightAddon;
    const hasLeftIcon = !!leftIcon;
    const hasRightIcon = !!rightIcon;

    return (
      <div className="w-full">
        {label && (
          <label htmlFor={inputId} className="block text-sm font-medium text-gray-300 mb-1.5">
            {label}
          </label>
        )}
        <div className="relative">
          {hasLeftAddon && (
            <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-gray-500 text-sm font-medium border-r border-gray-600 bg-gray-800/50 rounded-l-lg">
              {leftAddon}
            </div>
          )}
          {hasLeftIcon && (
            <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none text-gray-500" aria-hidden="true">
              {leftIcon}
            </div>
          )}
          <input
            ref={ref}
            id={inputId}
            className={cn(
              "w-full text-white placeholder-gray-500",
              "bg-gray-800/50 border border-gray-600 rounded-xl",
              "focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "transition-all duration-200",
              "placeholder-gray-500",
              "text-white",
              hasError && "border-red-500 focus:ring-red-500",
              hasLeftAddon && "pl-10",
              hasLeftIcon && "pl-10",
              hasRightAddon && "pr-10",
              hasRightIcon && "pr-10",
              "px-4 py-3 text-base",
              "rounded-xl",
              "bg-gray-800/50 backdrop-blur-sm",
              "border-gray-600",
              "hover:border-gray-500",
              "focus:ring-2 focus:ring-purple-500 focus:border-transparent"
            )}
            aria-invalid={hasError}
            aria-describedby={hasError ? `${inputId}-error` : helperText ? `${inputId}-helper` : hint ? `${inputId}-hint` : undefined}
            {...props}
          />
          {hasRightIcon && (
            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-gray-500" aria-hidden="true">
              {rightIcon}
            </div>
          )}
          {hasRightAddon && (
            <div className="absolute inset-y-0 right-0 flex items-center pr-3 pointer-events-none text-gray-500 text-sm font-medium border-l border-gray-600 bg-gray-800/50 rounded-r-lg">
              {rightAddon}
            </div>
          )}
        </div>
        {error && (
          <p id={`${inputId}-error`} className="mt-1.5 text-sm text-red-400 flex items-center gap-1" role="alert">
            <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 10-2 0v6a1 1 0 002 0V5z" clipRule="evenodd" />
            </svg>
            {error}
          </p>
        )}
        {!error && helperText && (
          <p id={`${inputId}-helper`} className="mt-1.5 text-sm text-gray-500">
            {helperText}
          </p>
        )}
        {!error && hint && (
          <p id={`${inputId}-hint`} className="mt-1.5 text-sm text-gray-500 flex items-center gap-1">
            <svg className="w-4 h-4 flex-shrink-0" fill="currentColor" viewBox="0 0 20 20" aria-hidden="true">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 10-2 0v6a1 1 0 002 0V5z" clipRule="evenodd" />
            </svg>
            {hint}
          </p>
        )}
      </div>
    );
  }
);

Input.displayName = "Input";

export default Input;