import React, { useEffect } from 'react';
import { createPortal } from 'react-dom';
import { AnimatePresence, motion } from 'framer-motion';

interface LayoutModalProps {
  isOpen: boolean;
  onClose?: () => void;
  children: React.ReactNode;
  closeOnBackdropClick?: boolean;
  closeOnEscape?: boolean;
  containerClassName?: string;
  contentClassName?: string;
  backdropClassName?: string;
  zIndexClassName?: string;
  respectLayoutBounds?: boolean;
}

export const LayoutModal: React.FC<LayoutModalProps> = ({
  isOpen,
  onClose,
  children,
  closeOnBackdropClick = true,
  closeOnEscape = true,
  containerClassName = '',
  contentClassName = '',
  backdropClassName = 'bg-black/60 backdrop-blur-md',
  zIndexClassName = 'z-[70]',
  respectLayoutBounds = true,
}) => {
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

  if (typeof document === 'undefined') {
    return null;
  }

  return createPortal(
    <AnimatePresence>
      {isOpen && (
        <motion.div
          className={`fixed ${zIndexClassName}`}
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
          role="presentation"
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
        >
          <motion.button
            type="button"
            aria-label="Close modal"
            className={`absolute inset-0 ${backdropClassName}`}
            onClick={closeOnBackdropClick ? onClose : undefined}
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
          />
          <div className="relative h-full w-full overflow-y-auto">
            <div
              className={`pointer-events-none min-h-full w-full flex items-center justify-center p-4 sm:p-6 ${containerClassName}`}
            >
              <motion.div
                className={`pointer-events-auto w-full flex justify-center ${contentClassName}`}
                initial={{ opacity: 0, scale: 0.9, y: 20 }}
                animate={{ opacity: 1, scale: 1, y: 0 }}
                exit={{ opacity: 0, scale: 0.95, y: 12 }}
                transition={{ type: 'spring', stiffness: 360, damping: 30, mass: 0.8 }}
              >
                {children}
              </motion.div>
            </div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body
  );
};
