import React from 'react';
import { useTranslation } from 'react-i18next';
import { Folder, MoreVertical, Pencil, Trash2 } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Collection } from '@/types/document';

interface CollectionCardProps {
  collection: Collection;
  onClick: (collection: Collection) => void;
  onEdit: (collection: Collection) => void;
  onDelete: (collection: Collection) => void;
}

export const CollectionCard: React.FC<CollectionCardProps> = ({
  collection,
  onClick,
  onEdit,
  onDelete,
}) => {
  const { t } = useTranslation();
  const [showMenu, setShowMenu] = React.useState(false);

  const getAccessLevelColor = (level: Collection['accessLevel']) => {
    switch (level) {
      case 'public':
        return 'bg-green-500/20 text-green-700 dark:text-green-400';
      case 'internal':
        return 'bg-blue-500/20 text-blue-700 dark:text-blue-400';
      case 'confidential':
        return 'bg-orange-500/20 text-orange-700 dark:text-orange-400';
      case 'restricted':
        return 'bg-red-500/20 text-red-700 dark:text-red-400';
    }
  };

  return (
    <GlassPanel className="hover:scale-105 transition-transform duration-200 relative cursor-pointer">
      {/* Access Badge */}
      <div className="absolute top-4 right-4 flex items-center gap-2">
        <span
          className={`text-xs px-2 py-1 rounded-full ${getAccessLevelColor(collection.accessLevel)}`}
        >
          {collection.accessLevel}
        </span>
      </div>

      {/* Folder Icon */}
      <div
        className="flex items-center justify-center h-32 mb-4 bg-white/10 rounded-lg"
        onClick={() => onClick(collection)}
      >
        <Folder className="w-12 h-12 text-amber-500" />
      </div>

      {/* Collection Info */}
      <div className="mb-4" onClick={() => onClick(collection)}>
        <h3
          className="text-sm font-semibold text-gray-800 dark:text-white mb-1 truncate"
          title={collection.name}
        >
          {collection.name}
        </h3>
        <p className="text-xs text-gray-600 dark:text-gray-400">
          {collection.itemCount} {collection.itemCount === 1 ? t('collection.file') : t('collection.files')}
        </p>
      </div>

      {/* Description */}
      {collection.description && (
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4 line-clamp-2">
          {collection.description}
        </p>
      )}

      {/* Actions */}
      <div className="flex items-center justify-between">
        <button
          onClick={() => onClick(collection)}
          className="flex-1 px-3 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600 transition-colors text-sm font-medium"
        >
          {t('collection.open')}
        </button>
        <div className="relative ml-2">
          <button
            onClick={(e) => {
              e.stopPropagation();
              setShowMenu(!showMenu);
            }}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <MoreVertical className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          </button>

          {showMenu && (
            <>
              <div className="fixed inset-0 z-40" onClick={() => setShowMenu(false)} />
              <div className="absolute right-0 mt-2 w-40 glass rounded-lg shadow-lg z-50 overflow-hidden">
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onEdit(collection);
                    setShowMenu(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2"
                >
                  <Pencil className="w-4 h-4" />
                  {t('common.edit')}
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    onDelete(collection);
                    setShowMenu(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2 text-red-500"
                >
                  <Trash2 className="w-4 h-4" />
                  {t('common.delete')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      {/* Metadata */}
      <div className="mt-3 pt-3 border-t border-gray-200 dark:border-gray-700 text-xs text-gray-500 dark:text-gray-400">
        {new Date(collection.createdAt).toLocaleDateString()}
      </div>
    </GlassPanel>
  );
};
