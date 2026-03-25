import React from 'react';
import { useMotionPolicy } from '@/motion';

interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export const LoadingSpinner: React.FC<LoadingSpinnerProps> = ({ size = 'md', className = '' }) => {
  const { effectiveTier } = useMotionPolicy();
  const sizeClasses = {
    sm: 'w-4 h-4 border-2',
    md: 'w-8 h-8 border-3',
    lg: 'w-12 h-12 border-4',
  };

  return (
    <div
      className={`${sizeClasses[size]} border-indigo-500 border-t-transparent rounded-full ${
        effectiveTier === 'off' ? '' : 'animate-spin'
      } ${className}`}
      role="status"
      aria-label="Loading"
    />
  );
};
