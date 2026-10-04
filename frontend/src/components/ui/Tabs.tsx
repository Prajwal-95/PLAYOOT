import React, { forwardRef, isValidElement, Children, cloneElement } from 'react';
import { cn } from "../../utils/cn";

interface TabsProps {
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
  variant?: "default" | "pills" | "underline";
  className?: string;
}

interface TabProps {
  value: string;
  children: React.ReactNode;
  disabled?: boolean;
  icon?: React.ReactNode;
  className?: string;
}

const Tab = forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & { value: string; disabled?: boolean; icon?: React.ReactNode; isActive?: boolean; onChange?: (value: string) => void; variant?: string }>(
  ({ value, children, disabled, icon, className, isActive, onChange, variant, ...props }, ref) => {
    const handleClick = () => {
      if (!disabled && onChange) {
        onChange(value);
      }
    };

    return (
      <button
        ref={ref}
        role="tab"
        aria-selected={isActive}
        aria-disabled={disabled}
        onClick={handleClick}
        disabled={disabled}
        className={cn(
          "relative flex items-center justify-center gap-2 font-medium rounded-xl transition-all duration-200",
          "focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          isActive
            ? "bg-gradient-to-r from-purple-600 to-violet-600 text-white shadow-playoot-sm"
            : "text-gray-400 hover:text-white hover:bg-gray-800/50",
          className
        )}
        {...props}
      >
        {icon && <span className="flex-shrink-0">{icon}</span>}
        {children}
      </button>
    );
  });

Tab.displayName = "Tab";

export const TabList = forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, children, ...props }, ref) => (
    <div
      ref={ref}
      role="tablist"
      className={cn(
        "flex gap-1",
        "bg-gray-800/50 backdrop-blur-sm rounded-xl p-1 border border-gray-700/50",
        className
      )}
      {...props}
    >
      {children}
    </div>
  )
);

TabList.displayName = "TabList";

export const TabPanels = ({ children, className }: { children: React.ReactNode; className?: string }) => (
  <div className={cn("mt-4", className)}>{children}</div>
);

TabPanels.displayName = "TabPanels";

export const TabPanel = ({ value, activeValue, children, className }: { 
  value: string; 
  activeValue: string; 
  children: React.ReactNode; 
  className?: string; 
}) => {
  if (value !== activeValue) return null;
  
  return (
    <div 
      role="tabpanel" 
      className={cn("animate-in fade-in slide-up-4 duration-300", className)}
    >
      {children}
    </div>
  );
};

TabPanel.displayName = "TabPanel";

interface TabInternalProps extends TabProps {
  isActive?: boolean;
  onChange?: (value: string) => void;
  variant?: string;
}

const TabInternal = forwardRef<HTMLButtonElement, React.ButtonHTMLAttributes<HTMLButtonElement> & TabProps & { isActive?: boolean; onChange?: (value: string) => void; variant?: string }>(
  ({ value, children, disabled, icon, className, isActive, onChange, variant, ...props }, ref) => {
    const handleClick = () => {
      if (!disabled && onChange) {
        onChange(value);
      }
    };

    return (
      <button
        ref={ref}
        role="tab"
        aria-selected={isActive}
        aria-disabled={disabled}
        onClick={handleClick}
        disabled={disabled}
        className={cn(
          "relative flex items-center justify-center gap-2 font-medium rounded-xl transition-all duration-200",
          "focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-gray-900",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          isActive
            ? "bg-gradient-to-r from-purple-600 to-violet-600 text-white shadow-playoot-sm"
            : "text-gray-400 hover:text-white hover:bg-gray-800/50",
          className
        )}
        {...props}
      >
        {icon && <span className="flex-shrink-0">{icon}</span>}
        {children}
      </button>
    );
  });

TabInternal.displayName = "Tab";

const Tabs = forwardRef<HTMLDivElement, TabsProps>(
  ({ value, onChange, children, variant = "default", className, ...props }, ref) => {
    return (
      <div ref={ref} className={cn("w-full", className)} {...props}>
        {React.Children.map(children, (child) => {
          if (React.isValidElement(child)) {
            const childProps = child.props as { value?: string };
            return React.cloneElement(child as React.ReactElement<any>, {
              value: childProps.value,
              isActive: childProps.value === value,
              onChange,
              variant,
            });
          }
          return child;
        })}
      </div>
    );
  }
);

Tabs.displayName = "Tabs";

export default Tabs;