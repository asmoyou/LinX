import React from 'react';
import { useTranslation } from 'react-i18next';
import { Clock, Folder, MoreVertical, Pencil, Trash2, FolderOpen, Shield, Globe, Users, Lock } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import { motion, AnimatePresence } from 'framer-motion';
import type { Collection } from '@/types/document';

interface CollectionCardProps {
  collection: Collection;
  onClick: (collection: Collection) => void;
  onEdit: (collection: Collection) => void;
  onDelete: (collection: Collection) => void;
  isDropTarget?: boolean;
  isDragActive?: boolean;
  onDragOver?: (event: React.DragEvent<HTMLDivElement>) => void;
  onDragLeave?: (event: React.DragEvent<HTMLDivElement>) => void;
  onDrop?: (event: React.DragEvent<HTMLDivElement>) => void;
}

export const CollectionCard: React.FC<CollectionCardProps> = ({
  collection,
  onClick,
  onEdit,
  onDelete,
  isDropTarget = false,
  isDragActive = false,
  onDragOver,
  onDragLeave,
  onDrop,
}) => {
  const { t } = useTranslation();
  const [showMenu, setShowMenu] = React.useState(false);
  const [isHovered, setIsHovered] = React.useState(false);
  const lastUpdatedAt = collection.updatedAt || collection.createdAt;

  const getAccessInfo = (level: Collection['accessLevel']) => {
    switch (level) {
      case 'public':
        return {
          color: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20',
          icon: <Globe className="w-3 h-3" />,
          label: t('document.visibilityPublic')
        };
      case 'internal':
        return {
          color: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/20',
          icon: <Users className="w-3 h-3" />,
          label: t('document.visibilityTeam')
        };
      case 'confidential':
        return {
          color: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20',
          icon: <Shield className="w-3 h-3" />,
          label: t('document.visibilityConfidential', 'Confidential')
        };
      case 'restricted':
        return {
          color: 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/20',
          icon: <Lock className="w-3 h-3" />,
          label: t('document.visibilityPrivate')
        };
      default:
        return {
          color: 'bg-gray-500/10 text-gray-600 dark:text-gray-400 border-gray-500/20',
          icon: <Folder className="w-3 h-3" />,
          label: level
        };
    }
  };

  const accessInfo = getAccessInfo(collection.accessLevel);

  const formatDateTime = (value: string) => {
    const parsed = new Date(value);
    if (Number.isNaN(parsed.getTime())) return value;
    return parsed.toLocaleString(undefined, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });
  };

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      whileHover={{ y: -5 }}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => {
        setIsHovered(false);
        setShowMenu(false);
      }}
    >
      <GlassPanel
        className={`h-full transition-all duration-300 relative cursor-pointer border-transparent hover:border-amber-500/30 overflow-hidden ${
          isDropTarget ? 'ring-2 ring-indigo-500 bg-indigo-500/5 scale-105' : ''
        }`}
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
      >
        {/* Access Badge */}
        <div className="absolute top-4 right-4 z-10">
          <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full border text-[10px] font-medium backdrop-blur-md shadow-sm ${accessInfo.color}`}>
            {accessInfo.icon}
            <span className="uppercase tracking-wider">{accessInfo.label}</span>
          </div>
        </div>

        {/* Folder Icon Container */}
        <div
          className={`relative flex flex-col items-center justify-center h-40 mb-4 rounded-xl transition-all duration-500 overflow-hidden group ${
            isDropTarget 
              ? 'bg-indigo-500/20 shadow-inner' 
              : 'bg-gradient-to-br from-white/10 to-white/5 dark:from-white/5 dark:to-transparent'
          }`}
          onClick={() => onClick(collection)}
        >
          {/* Animated Background Glow */}
          <div className={`absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-700 bg-gradient-to-br from-amber-500/10 via-transparent to-indigo-500/10`} />
          
          <div className="relative">
            <motion.div
              animate={{ 
                scale: isHovered ? 1.1 : 1,
                rotate: isHovered ? [0, -2, 2, 0] : 0 
              }}
              transition={{ duration: 0.4 }}
              className="relative z-10"
            >
              {isHovered || isDropTarget ? (
                <FolderOpen className={`w-16 h-16 ${isDropTarget ? 'text-indigo-500' : 'text-amber-500'} drop-shadow-xl`} />
              ) : (
                <Folder className="w-16 h-16 text-amber-500 drop-shadow-lg" />
              )}
            </motion.div>
            
            {/* Decoration elements for "layered" look */}
            <div className={`absolute -right-1 -bottom-1 w-8 h-8 rounded-full blur-2xl transition-colors duration-500 ${isDropTarget ? 'bg-indigo-500/40' : 'bg-amber-500/30'}`} />
            <div className={`absolute -left-1 -top-1 w-6 h-6 rounded-full blur-xl transition-colors duration-500 ${isDropTarget ? 'bg-blue-500/20' : 'bg-orange-500/20'}`} />
          </div>

          <AnimatePresence>
            {isDragActive && (
              <motion.div
                initial={{ opacity: 0, y: 10 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: 10 }}
                className="absolute bottom-4 left-0 right-0 text-center"
              >
                <span className={`px-3 py-1 rounded-full text-[10px] font-bold uppercase tracking-widest backdrop-blur-md border ${
                  isDropTarget 
                    ? 'bg-indigo-500 text-white border-indigo-400' 
                    : 'bg-white/20 text-indigo-700 dark:text-indigo-300 border-white/30'
                }`}>
                  {isDropTarget ? t('collection.dropToMove') : t('collection.dragHint')}
                </span>
              </motion.div>
            )}
          </AnimatePresence>
        </div>

        {/* Collection Info */}
        <div className="px-1 mb-4" onClick={() => onClick(collection)}>
          <h3
            className="text-base font-bold text-gray-800 dark:text-white mb-1 truncate group-hover:text-amber-500 transition-colors"
            title={collection.name}
          >
            {collection.name}
          </h3>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-amber-600 dark:text-amber-400 bg-amber-500/10 px-1.5 py-0.5 rounded">
              {collection.itemCount} {collection.itemCount === 1 ? t('collection.file') : t('collection.files')}
            </span>
            {collection.description && (
              <span className="text-xs text-gray-400 dark:text-gray-500 truncate max-w-[150px]">
                {collection.description}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 mt-auto">
          <button
            onClick={() => onClick(collection)}
            className="flex-1 px-4 py-2 bg-gradient-to-r from-amber-500 to-orange-500 text-white rounded-lg hover:from-amber-600 hover:to-orange-600 transition-all shadow-md shadow-amber-500/20 text-sm font-semibold"
          >
            {t('collection.open')}
          </button>
          
          <div className="relative">
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowMenu(!showMenu);
              }}
              className="p-2 hover:bg-white/10 dark:hover:bg-zinc-800/50 rounded-lg transition-colors border border-transparent hover:border-white/20"
            >
              <MoreVertical className="w-5 h-5 text-gray-600 dark:text-gray-400" />
            </button>

            <AnimatePresence>
              {showMenu && (
                <>
                  <motion.div 
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    className="fixed inset-0 z-40" 
                    onClick={(e) => {
                      e.stopPropagation();
                      setShowMenu(false);
                    }} 
                  />
                    <motion.div 
                    initial={{ opacity: 0, scale: 0.95, y: 10 }}
                    animate={{ opacity: 1, scale: 1, y: 0 }}
                    exit={{ opacity: 0, scale: 0.95, y: 10 }}
                    className="absolute right-0 bottom-full mb-2 w-44 bg-white dark:bg-zinc-900 rounded-xl shadow-2xl z-50 overflow-hidden border border-gray-200 dark:border-white/10"
                  >
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onEdit(collection);
                        setShowMenu(false);
                      }}
                      className="w-full px-4 py-3 text-left text-sm hover:bg-gray-100 dark:hover:bg-white/5 transition-colors flex items-center gap-3 text-gray-700 dark:text-gray-200"
                    >
                      <div className="w-8 h-8 rounded-lg bg-blue-500/10 flex items-center justify-center">
                        <Pencil className="w-4 h-4 text-blue-500" />
                      </div>
                      <span className="font-semibold">{t('common.edit')}</span>
                    </button>
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        onDelete(collection);
                        setShowMenu(false);
                      }}
                      className="w-full px-4 py-3 text-left text-sm hover:bg-red-50 dark:hover:bg-red-500/10 transition-colors flex items-center gap-3 text-red-600 dark:text-red-500"
                    >
                      <div className="w-8 h-8 rounded-lg bg-red-500/10 flex items-center justify-center">
                        <Trash2 className="w-4 h-4 text-red-600 dark:text-red-500" />
                      </div>
                      <span className="font-semibold">{t('common.delete')}</span>
                    </button>
                  </motion.div>
                </>
              )}
            </AnimatePresence>
          </div>
        </div>

        {/* Metadata */}
        <div className="mt-4 pt-4 border-t border-gray-100 dark:border-white/5 flex items-center justify-between text-[10px] text-gray-500 dark:text-gray-400">
          <div className="flex items-center gap-1.5 font-medium">
            <Clock className="w-3 h-3 text-amber-500/70" />
            <span>{formatDateTime(lastUpdatedAt)}</span>
          </div>
          <div className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
        </div>
      </GlassPanel>
    </motion.div>
  );
};

