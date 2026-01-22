import React from 'react';
import type { UseFormRegister, FieldError } from 'react-hook-form';

interface FormInputProps {
  id: string;
  name: string;
  type?: string;
  label: string;
  placeholder?: string;
  register: UseFormRegister<any>;
  error?: FieldError;
  disabled?: boolean;
  autoComplete?: string;
  autoFocus?: boolean;
}

export const FormInput: React.FC<FormInputProps> = ({
  id,
  name,
  type = 'text',
  label,
  placeholder,
  register,
  error,
  disabled = false,
  autoComplete,
  autoFocus = false,
}) => {
  return (
    <div>
      <label
        htmlFor={id}
        className="block text-sm font-medium text-zinc-700 dark:text-zinc-300 mb-2 transition-colors"
      >
        {label}
      </label>
      <input
        type={type}
        id={id}
        {...register(name)}
        disabled={disabled}
        className={`w-full px-4 py-3 bg-white/50 dark:bg-zinc-800/50 border ${
          error
            ? 'border-red-500 dark:border-red-400'
            : 'border-zinc-300 dark:border-zinc-700'
        } rounded-lg text-zinc-900 dark:text-zinc-100 placeholder-zinc-400 dark:placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-emerald-500 focus:border-transparent transition-all ${
          disabled 
            ? 'opacity-50 cursor-not-allowed bg-zinc-100 dark:bg-zinc-900' 
            : ''
        }`}
        placeholder={placeholder}
        autoComplete={autoComplete}
        autoFocus={autoFocus}
      />
      {error && (
        <p className="mt-1 text-sm text-red-500 dark:text-red-400">
          {error.message}
        </p>
      )}
    </div>
  );
};
