import React from 'react';

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({ 
  children, 
  className = '' 
}) => {
  return (
    <div className={`glass rounded-lg p-6 ${className}`}>
      {children}
    </div>
  );
};
