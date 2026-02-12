import React from 'react';

interface GlassPanelProps extends React.HTMLAttributes<HTMLDivElement> {
  children: React.ReactNode;
  hover?: boolean;
}

export const GlassPanel: React.FC<GlassPanelProps> = ({
  children,
  className = '',
  hover = false,
  ...divProps
}) => {
  return (
    <div
      className={`glass-panel rounded-[24px] p-6 ${hover ? 'hover-lift hover-glow' : ''} ${className}`}
      {...divProps}
    >
      {children}
    </div>
  );
};
