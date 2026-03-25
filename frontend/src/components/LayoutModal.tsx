import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';
import { X } from 'lucide-react';
import { getModalMotionPreset, useMotionPolicy } from '@/motion';

type ModalSize = 'xs' | 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl' | '5xl' | '6xl' | '7xl' | 'full';

const sizeClasses: Record<ModalSize, string> = {
  xs: 'max-w-xs',
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
  '3xl': 'max-w-3xl',
  '4xl': 'max-w-4xl',
  '5xl': 'max-w-5xl',
  '6xl': 'max-w-6xl',
  '7xl': 'max-w-7xl',
  full: 'max-w-[calc(100vw-2rem)] sm:max-w-[calc(100vw-4rem)]',
};

// Custom scrollbar styles
const scrollbarStyles = `
  .custom-scrollbar::-webkit-scrollbar {
    width: 6px;
  }
  .custom-scrollbar::-webkit-scrollbar-track {
    background: transparent;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(156, 163, 175, 0.3);
    border-radius: 10px;
  }
  .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(156, 163, 175, 0.5);
  }
  .dark .custom-scrollbar::-webkit-scrollbar-thumb {
    background: rgba(75, 85, 99, 0.4);
  }
  .dark .custom-scrollbar::-webkit-scrollbar-thumb:hover {
    background: rgba(75, 85, 99, 0.6);
  }
`;

interface LayoutModalProps {
  isOpen: boolean;
  onClose?: () => void;
  children: React.ReactNode;
  title?: React.ReactNode;
  description?: React.ReactNode;
  footer?: React.ReactNode;
  size?: ModalSize;
  closeOnBackdropClick?: boolean;
  closeOnEscape?: boolean;
  showCloseButton?: boolean;
  containerClassName?: string;
  contentClassName?: string;
  backdropClassName?: string;
  zIndexClassName?: string;
  respectLayoutBounds?: boolean;
  maxHeight?: string;
  isRaw?: boolean;
}

const Header: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div className={`px-5 py-3.5 border-b border-zinc-100 dark:border-zinc-800/60 shrink-0 ${className}`}>
    {children}
  </div>
);

const Body: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div className={`px-5 py-5 overflow-y-auto flex-1 min-h-0 custom-scrollbar ${className}`}>
    {children}
  </div>
);

const Footer: React.FC<{ children: React.ReactNode; className?: string }> = ({ children, className = '' }) => (
  <div className={`px-5 py-3.5 border-t border-zinc-100 dark:border-zinc-800/60 bg-zinc-50/30 dark:bg-zinc-900/30 shrink-0 ${className}`}>
    {children}
  </div>
);

export const LayoutModal: React.FC<LayoutModalProps> & {
  Header: typeof Header;
  Body: typeof Body;
  Footer: typeof Footer;
} = ({
  isOpen,
  onClose,
  children,
  title,
  description,
  footer,
  size = '2xl',
  closeOnBackdropClick = true,
  closeOnEscape = true,
  showCloseButton = true,
  containerClassName = '',
  contentClassName = '',
  backdropClassName = 'bg-black/40 backdrop-blur-sm',
  zIndexClassName = 'z-[70]',
  respectLayoutBounds = true,
  maxHeight = 'calc(100vh - 140px)',
  isRaw,
}) => {
  const { effectiveTier } = useMotionPolicy();

  useEffect(() => {
    if (!isOpen || !closeOnEscape || !onClose) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeOnEscape, onClose]);

  useEffect(() => {
    if (isOpen) {
      const originalStyle = window.getComputedStyle(document.body).overflow;
      document.body.style.overflow = 'hidden';
      return () => {
        document.body.style.overflow = originalStyle;
      };
    }
  }, [isOpen]);

  if (typeof document === 'undefined') {
    return null;
  }

  const hasCompoundComponents = React.Children.toArray(children).some(
    (child) =>
      React.isValidElement(child) &&
      (child.type === Header || child.type === Body || child.type === Footer)
  );

  const useRawLayout = isRaw !== undefined ? isRaw : (!title && !footer && !hasCompoundComponents);
  const modalMotionPreset = getModalMotionPreset(effectiveTier);

  return createPortal(
    <AnimatePresence initial={effectiveTier !== 'off'}>
      {isOpen && (
        <div 
          className={`fixed inset-0 flex items-center justify-center ${zIndexClassName} ${containerClassName}`}
          style={
            respectLayoutBounds
              ? {
                  top: 'var(--app-header-height, 4rem)',
                  left: 'var(--sidebar-width, 0px)',
                  right: 0,
                  bottom: 0,
                }
              : {
                  top: 0,
                  left: 0,
                  right: 0,
                  bottom: 0,
                }
          }
        >
          <style>{scrollbarStyles}</style>
          
          <motion.div
            initial={modalMotionPreset.backdrop.initial}
            animate={modalMotionPreset.backdrop.animate}
            exit={modalMotionPreset.backdrop.exit}
            transition={modalMotionPreset.backdrop.transition}
            className={`absolute inset-0 ${backdropClassName}`}
            onClick={closeOnBackdropClick ? onClose : undefined}
          />

          <div className="relative w-full h-full pointer-events-none">
            {useRawLayout ? (
              <div className="w-full h-full overflow-y-auto overscroll-contain pointer-events-auto custom-scrollbar p-4 sm:p-8">
                <div className="min-h-full w-full flex items-start sm:items-center justify-center">
                  <motion.div
                    variants={modalMotionPreset.variants}
                    initial="hidden"
                    animate="visible"
                    exit="exit"
                    className={`w-full flex justify-center ${contentClassName}`}
                  >
                    {children}
                  </motion.div>
                </div>
              </div>
            ) : (
              <div className="w-full h-full flex items-center justify-center p-4 sm:p-8">
                <motion.div
                  variants={modalMotionPreset.variants}
                  initial="hidden"
                  animate="visible"
                  exit="exit"
                  className={`pointer-events-auto relative w-full ${sizeClasses[size]} bg-white dark:bg-zinc-900 rounded-[22px] shadow-2xl overflow-hidden flex flex-col border border-zinc-100 dark:border-zinc-800/50 ${contentClassName}`}
                  style={{ maxHeight }}
                >
                  {/* Auto Header */}
                  {(title || (showCloseButton && onClose)) && !hasCompoundComponents && (
                    <div className="px-5 py-3.5 sm:px-6 border-b border-zinc-100 dark:border-zinc-800/60 flex items-center justify-between shrink-0">
                      <div className="flex-1 min-w-0">
                        {title && (
                          <h2 className="text-lg font-bold text-zinc-900 dark:text-white truncate">
                            {title}
                          </h2>
                        )}
                        {description && (
                          <p className="mt-0.5 text-xs text-zinc-500 dark:text-zinc-400">
                            {description}
                          </p>
                        )}
                      </div>
                      {showCloseButton && onClose && (
                        <button
                          onClick={onClose}
                          className="ml-4 p-1.5 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-lg transition-colors text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
                          aria-label="Close modal"
                        >
                          <X className="w-4.5 h-4.5" />
                        </button>
                      )}
                    </div>
                  )}

                  {/* Content */}
                  {hasCompoundComponents ? (
                    children
                  ) : (
                    <>
                      <div className="px-5 py-5 sm:px-6 overflow-y-auto flex-1 min-h-0 custom-scrollbar">
                        {children}
                      </div>
                      {footer && (
                        <div className="px-5 py-3.5 sm:px-6 border-t border-zinc-100 dark:border-zinc-800/60 bg-zinc-50/30 dark:bg-zinc-900/30 flex flex-col sm:flex-row justify-end gap-2.5 shrink-0">
                          {footer}
                        </div>
                      )}
                    </>
                  )}
                </motion.div>
              </div>
            )}
          </div>
        </div>
      )}
    </AnimatePresence>,
    document.body
  );
};

LayoutModal.Header = Header;
LayoutModal.Body = Body;
LayoutModal.Footer = Footer;
