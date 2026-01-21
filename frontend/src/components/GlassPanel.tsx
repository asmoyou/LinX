import React from 'react';

interface GlassPanelProps {
  children: React.ReactNode;
  className?: string;
  hover?: boolean;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({ 
  children, 
  className = '',
  hover = false 
}) => {
  return (
    <div className={`glass-panel rounded-[24px] p-6 ${hover ? 'hover-lift hover-glow' : ''} ${className}`}>
      {children}
    </div>
  );
};
