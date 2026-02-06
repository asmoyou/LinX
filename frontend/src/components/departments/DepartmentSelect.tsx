import React, { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Building2 } from 'lucide-react';
import { useDepartmentStore } from '@/stores';

interface DepartmentSelectProps {
  value?: string;
  onChange: (departmentId: string | undefined) => void;
  placeholder?: string;
  disabled?: boolean;
  className?: string;
  showAll?: boolean; // Show "All departments" option
}

export const DepartmentSelect: React.FC<DepartmentSelectProps> = ({
  value,
  onChange,
  placeholder,
  disabled = false,
  className = '',
  showAll = false,
}) => {
  const { t } = useTranslation();
  const { departments, fetchDepartments, isLoading } = useDepartmentStore();

  useEffect(() => {
    if (departments.length === 0) {
      fetchDepartments({ status: 'active' });
    }
  }, [departments.length, fetchDepartments]);

  return (
    <div className={`relative ${className}`}>
      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
        <Building2 className="h-4 w-4 text-zinc-400" />
      </div>
      <select
        value={value || ''}
        onChange={(e) => onChange(e.target.value || undefined)}
        disabled={disabled || isLoading}
        className="w-full pl-10 pr-4 py-2 bg-white dark:bg-zinc-800 border border-zinc-200 dark:border-zinc-700 rounded-lg text-sm text-zinc-900 dark:text-zinc-100 focus:outline-none focus:ring-2 focus:ring-emerald-500/50 focus:border-emerald-500 disabled:opacity-50 disabled:cursor-not-allowed appearance-none cursor-pointer"
      >
        {showAll && (
          <option value="">{t('departments.all', 'All Departments')}</option>
        )}
        {!showAll && (
          <option value="">
            {placeholder || t('departments.select', 'Select Department')}
          </option>
        )}
        {departments.map((dept) => (
          <option key={dept.id} value={dept.id}>
            {dept.name}
          </option>
        ))}
      </select>
      <div className="absolute inset-y-0 right-0 pr-3 flex items-center pointer-events-none">
        <svg className="h-4 w-4 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </div>
    </div>
  );
};
