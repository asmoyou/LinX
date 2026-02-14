import React from 'react';
import { useTranslation } from 'react-i18next';
import { ChevronRight, Home, Folder } from 'lucide-react';
import { motion } from 'framer-motion';
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
    <motion.nav 
      initial={{ opacity: 0, x: -10 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-1.5 mb-6 text-sm"
    >
      <button
        onClick={onNavigateRoot}
        className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white/10 dark:bg-white/5 text-gray-600 dark:text-gray-400 hover:bg-white/20 dark:hover:bg-white/10 hover:text-indigo-500 transition-all font-medium border border-transparent hover:border-indigo-500/20 group"
      >
        <Home className="w-3.5 h-3.5 group-hover:scale-110 transition-transform" />
        {t('collection.breadcrumbRoot')}
      </button>
      
      <ChevronRight className="w-4 h-4 text-gray-400 mx-1" />
      
      <div className="flex items-center gap-2 px-3 py-1.5 rounded-lg bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20 font-semibold shadow-sm shadow-indigo-500/5">
        <Folder className="w-3.5 h-3.5" />
        <span className="truncate max-w-[200px] md:max-w-xs">
          {collection.name}
        </span>
      </div>
    </motion.nav>
  );
};

