import React, { useEffect } from 'react';

interface LayoutModalProps {
  isOpen: boolean;
  onClose?: () => void;
  children: React.ReactNode;
  closeOnBackdropClick?: boolean;
  closeOnEscape?: boolean;
  containerClassName?: string;
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
  backdropClassName = 'bg-black/60 backdrop-blur-md animate-in fade-in duration-200',
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

  if (!isOpen) return null;

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
        className={`absolute inset-0 ${backdropClassName}`}
        onClick={closeOnBackdropClick ? onClose : undefined}
      />
      <div
        className={`relative h-full w-full pointer-events-none flex items-center justify-center p-4 sm:p-6 ${containerClassName}`}
      >
        <div className="pointer-events-auto w-full flex justify-center">{children}</div>
      </div>
    </div>
  );
};
