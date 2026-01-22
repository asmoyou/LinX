import React from 'react';
import { Loader2 } from 'lucide-react';
import type { LucideProps } from 'lucide-react';

interface SubmitButtonProps {
  isLoading: boolean;
  loadingText: string;
  text: string;
  icon?: React.ComponentType<LucideProps>;
  disabled?: boolean;
  className?: string;
  variant?: 'primary' | 'secondary' | 'danger';
}

export const SubmitButton: React.FC<SubmitButtonProps> = ({
  isLoading,
  loadingText,
  text,
  icon: Icon,
  disabled = false,
  className = '',
  variant = 'primary',
}) => {
  const variantClasses = {
    primary: 'bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-600 hover:to-teal-600 shadow-emerald-500/25',
    secondary: 'bg-gradient-to-r from-zinc-500 to-zinc-600 hover:from-zinc-600 hover:to-zinc-700 shadow-zinc-500/25',
    danger: 'bg-gradient-to-r from-red-500 to-red-600 hover:from-red-600 hover:to-red-700 shadow-red-500/25',
  };

  const isDisabled = isLoading || disabled;

  return (
    <button
      type="submit"
      disabled={isDisabled}
      className={`w-full py-3 px-4 ${variantClasses[variant]} text-white font-medium rounded-lg transition-all duration-200 flex items-center justify-center gap-2 shadow-lg ${
        isDisabled
          ? 'opacity-75 cursor-not-allowed scale-[0.98]'
          : 'hover:scale-[1.02] active:scale-[0.98]'
      } ${className}`}
    >
      {isLoading ? (
        <>
          <Loader2 className="w-5 h-5 animate-spin" />
          <span className="animate-pulse">{loadingText}</span>
        </>
      ) : (
        <>
          {Icon && <Icon className="w-5 h-5" />}
          {text}
        </>
      )}
    </button>
  );
};
