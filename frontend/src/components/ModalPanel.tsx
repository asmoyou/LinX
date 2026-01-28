import React from 'react';

interface ModalPanelProps {
  children: React.ReactNode;
  className?: string;
}

export const ModalPanel: React.FC<ModalPanelProps> = ({ 
  children, 
  className = '' 
}) => {
  return (
    <div className={`modal-panel rounded-[24px] p-6 ${className}`}>
      {children}
    </div>
  );
};
