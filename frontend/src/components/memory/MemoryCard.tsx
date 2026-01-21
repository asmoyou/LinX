import React from 'react';
import { Brain, User, Building, Clock, Tag, Share2, TrendingUp } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Memory } from '@/types/memory';

interface MemoryCardProps {
  memory: Memory;
  onClick: (memory: Memory) => void;
  showRelevance?: boolean;
}

export const MemoryCard: React.FC<MemoryCardProps> = ({ memory, onClick, showRelevance = false }) => {
  const getTypeIcon = (type: Memory['type']) => {
    switch (type) {
      case 'agent':
        return <Brain className="w-5 h-5 text-blue-500" />;
      case 'company':
        return <Building className="w-5 h-5 text-green-500" />;
      case 'user_context':
        return <User className="w-5 h-5 text-purple-500" />;
    }
  };

  const getTypeLabel = (type: Memory['type']) => {
    switch (type) {
      case 'agent':
        return 'Agent Memory';
      case 'company':
        return 'Company Memory';
      case 'user_context':
        return 'User Context';
    }
  };

  const getTypeColor = (type: Memory['type']) => {
    switch (type) {
      case 'agent':
        return 'bg-blue-500/20 text-blue-700 dark:text-blue-400';
      case 'company':
        return 'bg-green-500/20 text-green-700 dark:text-green-400';
      case 'user_context':
        return 'bg-purple-500/20 text-purple-700 dark:text-purple-400';
    }
  };

  return (
    <div onClick={() => onClick(memory)} className="cursor-pointer">
      <GlassPanel className="hover:scale-[1.02] transition-transform duration-200">
        {/* Header */}
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            {getTypeIcon(memory.type)}
            <span className={`text-xs px-2 py-1 rounded-full ${getTypeColor(memory.type)}`}>
              {getTypeLabel(memory.type)}
            </span>
          </div>
          {showRelevance && memory.relevanceScore !== undefined && (
            <div className="flex items-center gap-1 text-xs text-gray-600 dark:text-gray-400">
              <TrendingUp className="w-3 h-3" />
              {(memory.relevanceScore * 100).toFixed(0)}%
            </div>
          )}
        </div>

        {/* Content */}
        <div className="mb-3">
          {memory.summary && (
            <p className="text-sm font-medium text-gray-800 dark:text-white mb-2">
              {memory.summary}
            </p>
          )}
          <p className="text-sm text-gray-600 dark:text-gray-400 line-clamp-3">
            {memory.content}
          </p>
        </div>

        {/* Tags */}
        {memory.tags.length > 0 && (
          <div className="flex flex-wrap gap-1 mb-3">
            {memory.tags.slice(0, 3).map((tag) => (
              <span key={tag} className="flex items-center gap-1 text-xs px-2 py-0.5 bg-white/20 rounded-full text-gray-700 dark:text-gray-300">
                <Tag className="w-3 h-3" />
                {tag}
              </span>
            ))}
            {memory.tags.length > 3 && (
              <span className="text-xs px-2 py-0.5 bg-white/20 rounded-full text-gray-700 dark:text-gray-300">
                +{memory.tags.length - 3}
              </span>
            )}
          </div>
        )}

        {/* Metadata */}
        <div className="flex items-center justify-between text-xs text-gray-500 dark:text-gray-400 pt-3 border-t border-gray-200 dark:border-gray-700">
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-1">
              <Clock className="w-3 h-3" />
              {new Date(memory.createdAt).toLocaleDateString()}
            </div>
            {memory.agentName && (
              <span className="truncate max-w-[120px]" title={memory.agentName}>
                {memory.agentName}
              </span>
            )}
          </div>
          {memory.isShared && (
            <div className="flex items-center gap-1 text-primary-500">
              <Share2 className="w-3 h-3" />
              <span>Shared</span>
            </div>
          )}
        </div>
      </GlassPanel>
    </div>
  );
};
