import React, { forwardRef, useState } from 'react';
import { cn } from "../../utils/cn";

interface AvatarProps extends React.HTMLAttributes<HTMLDivElement> {
  src?: string;
  alt?: string;
  fallback?: string;
  size?: "xs" | "sm" | "md" | "lg" | "xl" | "2xl";
  shape?: "circle" | "square";
  status?: "online" | "offline" | "busy" | "away";
  statusPosition?: "bottom-right" | "bottom-left" | "top-right" | "top-left";
  border?: boolean;
}

export const Avatar = forwardRef<HTMLDivElement, AvatarProps>(
  ({ 
    className, 
    src, 
    alt, 
    fallback, 
    size = "md", 
    shape = "circle", 
    status, 
    statusPosition = "bottom-right",
    border = true,
    ...props 
  }, ref) => {
    const sizes = {
      xs: "w-6 h-6 text-xs",
      sm: "w-8 h-8 text-sm",
      md: "w-10 h-10 text-base",
      lg: "w-12 h-12 text-lg",
      xl: "w-16 h-16 text-xl",
      "2xl": "w-24 h-24 text-2xl",
    };

    const statusSizes = {
      xs: "w-2 h-2",
      sm: "w-2.5 h-2.5",
      md: "w-3 h-3",
      lg: "w-3.5 h-3.5",
      xl: "w-4 h-4",
      "2xl": "w-5 h-5",
    };

    const statusPositions = {
      "bottom-right": "bottom-0 right-0",
      "bottom-left": "bottom-0 left-0",
      "top-right": "top-0 right-0",
      "top-left": "top-0 left-0",
    };

    const statusColors = {
      online: "bg-emerald-500 border-white dark:border-gray-900",
      offline: "bg-gray-500 border-white dark:border-gray-900",
      busy: "bg-red-500 border-white dark:border-gray-900",
      away: "bg-amber-500 border-white dark:border-gray-900",
    };

    const shapeClass = shape === "circle" ? "rounded-full" : "rounded-xl";

    const [imageError, setImageError] = useState(false);

    const renderContent = () => {
      if (!imageError && src) {
        return (
          <img
            src={src}
            alt={alt}
            className={cn("w-full h-full object-cover", shapeClass)}
            onError={() => setImageError(true)}
          />
        );
      }

      return (
        <div className={cn("w-full h-full flex items-center justify-center", shapeClass)}>
          {fallback ? (
            <span className="font-medium text-white select-none">
              {fallback}
            </span>
          ) : (
            <svg className="w-1/2 h-1/2 text-gray-500" fill="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path d="M24 20.993V24H0v-2.996A14.977 14.977 0 0112.004 15c4.904 0 9.26 2.354 11.996 5.993zM16.002 8.999a4 4 0 11-8 0 4 4 0 018 0z" />
            </svg>
          )}
        </div>
      );
    };

    return (
      <div
        ref={ref}
        className={cn(
          "relative inline-flex items-center justify-center overflow-hidden bg-gray-700/50",
          sizes[size],
          shapeClass,
          "bg-gray-700/50",
          className
        )}
        {...props}
      >
        {renderContent()}
        {status && (
          <span
            className={cn(
              "absolute rounded-full border-2",
              sizes[size],
              statusSizes[size],
              statusColors[status],
              statusPositions[statusPosition]
            )}
            aria-label={`Status: ${status}`}
          />
        )}
        {border && (
          <div className={cn("absolute inset-0 border-2", "border-purple-500/50", shapeClass)} />
        )}
      </div>
    );
  }
);

Avatar.displayName = "Avatar";

export default Avatar;