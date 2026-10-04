import React, { forwardRef, useState, useRef, useEffect } from 'react';
import { cn } from "../../utils/cn";
import { ChevronDown, ChevronUp, Check } from "lucide-react";

interface SelectOption {
  value: string;
  label: string;
  disabled?: boolean;
  icon?: React.ReactNode;
}

interface SelectProps extends Omit<React.SelectHTMLAttributes<HTMLSelectElement>, "onChange"> {
  label?: string;
  error?: string;
  helperText?: string;
  options: SelectOption[];
  placeholder?: string;
  searchable?: boolean;
  clearable?: boolean;
  leftIcon?: React.ReactNode;
  onChange?: (value: string) => void;
}

export const Select = forwardRef<HTMLDivElement, SelectProps>(
  ({ 
    className, 
    label, 
    error, 
    helperText, 
    options, 
    placeholder, 
    searchable = false, 
    clearable = false,
    leftIcon,
    onChange,
    ...props 
  }, ref) => {
    const [isOpen, setIsOpen] = useState(false);
    const [searchQuery, setSearchQuery] = useState("");
    const selectRef = useRef<HTMLDivElement>(null);
    const inputRef = useRef<HTMLInputElement>(null);
    const [focusedIndex, setFocusedIndex] = useState(-1);

    const filteredOptions = options.filter(opt => 
      !opt.disabled && 
      (opt.label.toLowerCase().includes(searchQuery.toLowerCase()) || 
       opt.value.toLowerCase().includes(searchQuery.toLowerCase()))
    );

    useEffect(() => {
      const handleClickOutside = (e: MouseEvent) => {
        if (selectRef.current && !selectRef.current.contains(e.target as Node)) {
          setIsOpen(false);
        }
      };

      document.addEventListener('mousedown', handleClickOutside);
      return () => document.removeEventListener('mousedown', handleClickOutside);
    }, []);

    const handleKeyDown = (e: React.KeyboardEvent) => {
      const visibleOptions = filteredOptions.filter(opt => !opt.disabled);
      if (visibleOptions.length === 0) return;

      switch (e.key) {
        case 'ArrowDown':
          e.preventDefault();
          setFocusedIndex(prev => Math.min(prev + 1, visibleOptions.length - 1));
          break;
        case 'ArrowUp':
          e.preventDefault();
          setFocusedIndex(prev => Math.max(prev - 1, 0));
          break;
        case 'Enter':
        case ' ':
          e.preventDefault();
          if (focusedIndex >= 0 && visibleOptions[focusedIndex]) {
            onChange?.(visibleOptions[focusedIndex].value);
            setIsOpen(false);
            setSearchQuery("");
            setFocusedIndex(-1);
          }
          break;
        case 'Escape':
          setIsOpen(false);
          setSearchQuery("");
          setFocusedIndex(-1);
          break;
        case 'Tab':
          setIsOpen(false);
          setSearchQuery("");
          setFocusedIndex(-1);
          break;
      }
    };

    const handleChange = (value: string) => {
      onChange?.(value);
      if (!searchable) {
        setIsOpen(false);
      }
    };

    const renderOptions = () => {
      if (filteredOptions.length === 0) {
        return (
          <div className="px-4 py-3 text-center text-gray-500 text-sm">
            {searchable && searchQuery ? "No matching options" : "No options available"}
          </div>
        );
      }

      return (
        filteredOptions.map((option, index) => (
          <button
            key={option.value}
            type="button"
            role="option"
            aria-selected={props.value === option.value}
            aria-disabled={option.disabled}
            disabled={option.disabled}
            className={cn(
              "w-full px-4 py-3 text-left transition-colors",
              "flex items-center gap-3",
              focusedIndex === index && "bg-purple-600/30",
              !option.disabled && "hover:bg-gray-800/50",
              option.disabled && "opacity-50 cursor-not-allowed"
            )}
            onClick={() => {
              if (!option.disabled) {
                handleChange(option.value);
              }
            }}
            onMouseEnter={() => setFocusedIndex(index)}
          >
            {option.icon && <span className="flex-shrink-0">{option.icon}</span>}
            <span className="flex-1 truncate">{option.label}</span>
            {props.value === option.value && (
              <Check className="w-5 h-5 text-purple-400 flex-shrink-0" />
            )}
          </button>
        ))
      );
    };

    const selectedOption = options.find(opt => opt.value === props.value);
    const displayValue = selectedOption?.label || "Select...";

    return (
      <div className="w-full" ref={selectRef as React.RefObject<HTMLDivElement>}>
        {label && (
          <label className="block text-sm font-medium text-gray-300 mb-1.5">
            {label}
          </label>
        )}
        <div className="relative">
          <div
            ref={selectRef}
            className={cn(
              "relative",
              "bg-gray-800/50 backdrop-blur-sm",
              "border border-gray-600 rounded-xl",
              "focus-within:ring-2 focus-within:ring-purple-500 focus-within:border-transparent",
              "disabled:opacity-50 disabled:cursor-not-allowed",
              "transition-all duration-200",
              error && "border-red-500",
              className
            )}
          >
            <button
              type="button"
              className="w-full flex items-center justify-between px-4 py-3 text-left"
              onClick={() => !props.disabled && setIsOpen(!isOpen)}
              onKeyDown={handleKeyDown}
              disabled={props.disabled}
              aria-haspopup="listbox"
              aria-expanded={isOpen}
            >
              {leftIcon && <span className="mr-3 text-gray-400">{leftIcon}</span>}
              <span className={cn(
                "flex-1 truncate",
                props.value ? "text-white" : "text-gray-500"
              )}>
                {displayValue}
              </span>
              {clearable && props.value && (
                <button
                  type="button"
                  onClick={(e) => {
                    e.stopPropagation();
                    handleChange("");
                  }}
                  className="ml-2 p-1 text-gray-400 hover:text-white rounded-full hover:bg-gray-700 transition-colors"
                  aria-label="Clear selection"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              )}
              <svg 
                className={cn(
                  "w-5 h-5 text-gray-400 transition-transform duration-200",
                  isOpen && "rotate-180"
                )}
                fill="none" 
                stroke="currentColor" 
                viewBox="0 0 24 24" 
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
              </svg>
            </button>

            {isOpen && (
              <React.Fragment>
                {searchable && (
                  <div className="p-3 border-b border-gray-700">
                    <input
                      ref={inputRef}
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      onClick={(e) => e.stopPropagation()}
                      placeholder="Search options..."
                      className="w-full px-3 py-2 bg-gray-800 border border-gray-600 rounded-lg text-white placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-purple-500 focus:border-transparent"
                      autoFocus
                    />
                  </div>
                )}
                <div className="max-h-60 overflow-y-auto py-1">
                  {renderOptions()}
                </div>
              </React.Fragment>
            )}
          </div>
          {error && (
            <p className="mt-1.5 text-sm text-red-400" role="alert">{error}</p>
          )}
          {!error && helperText && (
            <p className="mt-1.5 text-sm text-gray-500">{helperText}</p>
          )}
        </div>
      </div>
    );
  }
);

Select.displayName = "Select";

export default Select;