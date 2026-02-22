import React, { useEffect, useState } from 'react';

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
  const [isRendered, setIsRendered] = useState(isOpen);
  const [isVisible, setIsVisible] = useState(false);

  /* eslint-disable react-hooks/set-state-in-effect */
  useEffect(() => {
    if (isOpen) {
      setIsRendered(true);
      const raf = window.requestAnimationFrame(() => setIsVisible(true));
      return () => window.cancelAnimationFrame(raf);
    }

    setIsVisible(false);
    const timeout = window.setTimeout(() => setIsRendered(false), 200);
    return () => window.clearTimeout(timeout);
  }, [isOpen]);
  /* eslint-enable react-hooks/set-state-in-effect */

  useEffect(() => {
    if (!isRendered || !closeOnEscape || !onClose) return;

    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        onClose();
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isRendered, closeOnEscape, onClose]);

  if (!isRendered) return null;

  return (
    <div
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
    >
      <button
        type="button"
        aria-label="Close modal"
        className={`absolute inset-0 transition-opacity duration-200 ease-out ${isVisible ? 'opacity-100' : 'opacity-0'} ${backdropClassName}`}
        onClick={closeOnBackdropClick ? onClose : undefined}
      />
      <div
        className="relative h-full w-full overflow-y-auto"
      >
        <div
          className={`pointer-events-none min-h-full w-full flex items-center justify-center p-4 sm:p-6 ${containerClassName}`}
        >
          <div
            className={`pointer-events-auto w-full flex justify-center transition-all duration-200 ease-out ${isVisible ? 'opacity-100 scale-100 translate-y-0' : 'opacity-0 scale-95 translate-y-2'} ${contentClassName}`}
          >
            {children}
          </div>
        </div>
      </div>
    </div>
  );
};
