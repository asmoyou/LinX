import React from 'react';
import { X, Brain, User, Building, Clock, Tag, Share2, TrendingUp, Link as LinkIcon } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import type { Memory } from '@/types/memory';

interface MemoryDetailViewProps {
  memory: Memory | null;
  isOpen: boolean;
  onClose: () => void;
  onShare?: (memory: Memory) => void;
}

export const MemoryDetailView: React.FC<MemoryDetailViewProps> = ({ 
  memory, 
  isOpen, 
  onClose,
  onShare 
}) => {
  if (!isOpen || !memory) return null;

  const getTypeIcon = (type: Memory['type']) => {
    switch (type) {
      case 'agent':
        return <Brain className="w-6 h-6 text-blue-500" />;
      case 'company':
        return <Building className="w-6 h-6 text-green-500" />;
      case 'user_context':
        return <User className="w-6 h-6 text-purple-500" />;
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

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm">
      <GlassPanel className="w-full max-w-3xl max-h-[90vh] overflow-y-auto">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <div className="flex items-center gap-3">
            {getTypeIcon(memory.type)}
            <h2 className="text-2xl font-bold text-gray-800 dark:text-white">
              {getTypeLabel(memory.type)}
            </h2>
          </div>
          <div className="flex items-center gap-2">
            {onShare && (
              <button
                onClick={() => onShare(memory)}
                className="p-2 hover:bg-white/20 rounded-lg transition-colors"
                title="Share Memory"
              >
                <Share2 className="w-5 h-5 text-gray-700 dark:text-gray-300" />
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
            >
              <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
            </button>
          </div>
        </div>

        {/* Relevance Score */}
        {memory.relevanceScore !== undefined && (
          <div className="mb-6 p-4 bg-primary-500/10 border border-primary-500/30 rounded-lg">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <TrendingUp className="w-5 h-5 text-primary-500" />
                <span className="text-sm font-medium text-gray-800 dark:text-white">
                  Relevance Score
                </span>
              </div>
              <span className="text-2xl font-bold text-primary-500">
                {(memory.relevanceScore * 100).toFixed(0)}%
              </span>
            </div>
            <div className="mt-2 w-full h-2 bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
              <div
                className="h-full bg-primary-500 transition-all duration-500"
                style={{ width: `${memory.relevanceScore * 100}%` }}
              />
            </div>
          </div>
        )}

        {/* Summary */}
        {memory.summary && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">Summary</h3>
            <p className="text-gray-700 dark:text-gray-300 bg-white/10 p-4 rounded-lg">
              {memory.summary}
            </p>
          </div>
        )}

        {/* Content */}
        <div className="mb-6">
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">Content</h3>
          <div className="text-gray-700 dark:text-gray-300 bg-white/10 p-4 rounded-lg whitespace-pre-wrap">
            {memory.content}
          </div>
        </div>

        {/* Metadata Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-6">
          <div className="p-4 bg-white/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-5 h-5 text-blue-500" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Created</span>
            </div>
            <p className="text-gray-800 dark:text-white font-medium">
              {new Date(memory.createdAt).toLocaleString()}
            </p>
          </div>

          {memory.updatedAt && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Clock className="w-5 h-5 text-green-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">Updated</span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">
                {new Date(memory.updatedAt).toLocaleString()}
              </p>
            </div>
          )}

          {memory.agentName && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <Brain className="w-5 h-5 text-blue-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">Agent</span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">{memory.agentName}</p>
            </div>
          )}

          {memory.userName && (
            <div className="p-4 bg-white/10 rounded-lg">
              <div className="flex items-center gap-2 mb-2">
                <User className="w-5 h-5 text-purple-500" />
                <span className="text-sm text-gray-600 dark:text-gray-400">User</span>
              </div>
              <p className="text-gray-800 dark:text-white font-medium">{memory.userName}</p>
            </div>
          )}
        </div>

        {/* Tags */}
        {memory.tags.length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">Tags</h3>
            <div className="flex flex-wrap gap-2">
              {memory.tags.map((tag) => (
                <span
                  key={tag}
                  className="flex items-center gap-1 px-3 py-1 bg-white/20 rounded-full text-sm text-gray-700 dark:text-gray-300"
                >
                  <Tag className="w-3 h-3" />
                  {tag}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Related Items */}
        {memory.metadata && Object.keys(memory.metadata).length > 0 && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-3">
              Related Items
            </h3>
            <div className="space-y-2">
              {memory.metadata.taskId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Task: {memory.metadata.taskId}
                  </span>
                </div>
              )}
              {memory.metadata.goalId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Goal: {memory.metadata.goalId}
                  </span>
                </div>
              )}
              {memory.metadata.documentId && (
                <div className="flex items-center gap-2 p-3 bg-white/10 rounded-lg">
                  <LinkIcon className="w-4 h-4 text-gray-600 dark:text-gray-400" />
                  <span className="text-sm text-gray-700 dark:text-gray-300">
                    Document: {memory.metadata.documentId}
                  </span>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Sharing Status */}
        {memory.isShared && (
          <div className="p-4 bg-primary-500/10 border border-primary-500/30 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Share2 className="w-5 h-5 text-primary-500" />
              <span className="text-sm font-medium text-gray-800 dark:text-white">
                Shared Memory
              </span>
            </div>
            {memory.sharedWith && memory.sharedWith.length > 0 && (
              <p className="text-sm text-gray-600 dark:text-gray-400">
                Shared with: {memory.sharedWith.join(', ')}
              </p>
            )}
          </div>
        )}
      </GlassPanel>
    </div>
  );
};
