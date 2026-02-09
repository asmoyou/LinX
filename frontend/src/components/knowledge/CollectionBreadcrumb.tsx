import React from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronRight } from 'lucide-react';
import type { Collection } from '@/types/document';

interface CollectionBreadcrumbProps {
  collection: Collection | null;
  onNavigateRoot: () => void;
}

export const CollectionBreadcrumb: React.FC<CollectionBreadcrumbProps> = ({
  collection,
  onNavigateRoot,
}) => {
  const { t } = useTranslation();
  if (!collection) return null;

  return (
    <nav className="flex items-center gap-2 mb-4 text-sm">
      <button
        onClick={onNavigateRoot}
        className="text-indigo-500 hover:text-indigo-600 dark:text-indigo-400 dark:hover:text-indigo-300 font-medium transition-colors"
      >
        {t('collection.breadcrumbRoot')}
      </button>
      <ChevronRight className="w-4 h-4 text-gray-400" />
      <span className="text-gray-800 dark:text-white font-medium truncate max-w-xs">
        {collection.name}
      </span>
    </nav>
  );
};
