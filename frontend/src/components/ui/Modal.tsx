import React, { forwardRef, useEffect } from 'react';
import { cn } from "../../utils/cn";
import { X } from "lucide-react";

interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  description?: string;
  children: React.ReactNode;
  size?: "sm" | "md" | "lg" | "xl" | "full";
  showCloseButton?: boolean;
  closeOnOverlayClick?: boolean;
  closeOnEscape?: boolean;
  className?: string;
}

export const Modal = forwardRef<HTMLDivElement, ModalProps>(
  ({ 
    isOpen, 
    onClose, 
    title, 
    description, 
    children, 
    size = "md", 
    showCloseButton = true,
    closeOnOverlayClick = true,
    closeOnEscape = true,
    className,
    ...props 
  }, ref) => {
    useEffect(() => {
      if (!isOpen) return;

      const handleEscape = (e: KeyboardEvent) => {
        if (e.key === "Escape" && closeOnEscape) {
          onClose();
        }
      };

      document.addEventListener("keydown", handleEscape);
      document.body.style.overflow = "hidden";

      return () => {
        document.removeEventListener("keydown", handleEscape);
        document.body.style.overflow = "unset";
      };
    }, [isOpen, closeOnEscape, onClose]);

    if (!isOpen) return null;

    const sizes = {
      sm: "max-w-sm",
      md: "max-w-md",
      lg: "max-w-lg",
      xl: "max-w-xl",
      full: "max-w-4xl",
    };

    const handleOverlayClick = (e: React.MouseEvent) => {
      if (closeOnOverlayClick && e.target === e.currentTarget) {
        onClose();
      }
    };

    return (
      <div 
        className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm"
        onClick={handleOverlayClick}
        role="dialog"
        aria-modal="true"
        aria-labelledby={title ? "modal-title" : undefined}
        aria-describedby={description ? "modal-description" : undefined}
      >
        <div 
          ref={ref}
          className={cn(
            "w-full animate-in fade-in zoom-in-95 duration-200",
            "bg-gray-900/95 backdrop-blur-xl border border-gray-700/50 rounded-2xl shadow-playoot-lg",
            sizes[size],
            "max-h-[90vh] overflow-hidden flex flex-col",
            className
          )}
          {...props}
        >
          {(title || showCloseButton) && (
            <div className="flex items-start justify-between p-6 border-b border-gray-700/50">
              <div>
                {title && (
                  <h2 id="modal-title" className="text-xl font-bold text-white">
                    {title}
                  </h2>
                )}
                {description && (
                  <p id="modal-description" className="mt-1 text-sm text-gray-400">
                    {description}
                  </p>
                )}
              </div>
              {showCloseButton && (
                <button
                  onClick={onClose}
                  className="p-2 rounded-xl text-gray-400 hover:text-white hover:bg-gray-800/50 transition-colors"
                  aria-label="Close"
                >
                  <X className="w-5 h-5" />
                </button>
              )}
            </div>
          )}
          <div className="flex-1 overflow-y-auto p-6">
            {children}
          </div>
        </div>
      </div>
    );
  }
);

Modal.displayName = "Modal";

export default Modal;