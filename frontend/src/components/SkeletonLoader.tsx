import React from 'react';

interface SkeletonLoaderProps {
  variant?: 'text' | 'card' | 'avatar' | 'rect';
  width?: string;
  height?: string;
  className?: string;
}

export const SkeletonLoader: React.FC<SkeletonLoaderProps> = ({
  variant = 'text',
  width,
  height,
  className = '',
}) => {
  const baseClasses = 'animate-pulse bg-gray-300 dark:bg-gray-700';

  const variantClasses = {
    text: 'h-4 rounded',
    card: 'h-48 rounded-lg',
    avatar: 'w-12 h-12 rounded-full',
    rect: 'rounded-lg',
  };

  const style = {
    width: width || (variant === 'text' ? '100%' : undefined),
    height: height || undefined,
  };

  return <div className={`${baseClasses} ${variantClasses[variant]} ${className}`} style={style} />;
};

export const SkeletonCard: React.FC = () => {
  return (
    <div className="glass rounded-lg p-6 space-y-4">
      <div className="flex items-center gap-3">
        <SkeletonLoader variant="avatar" />
        <div className="flex-1 space-y-2">
          <SkeletonLoader variant="text" width="60%" />
          <SkeletonLoader variant="text" width="40%" />
        </div>
      </div>
      <SkeletonLoader variant="text" />
      <SkeletonLoader variant="text" width="80%" />
      <SkeletonLoader variant="text" width="90%" />
    </div>
  );
};
