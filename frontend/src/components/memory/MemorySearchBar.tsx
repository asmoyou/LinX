import React from 'react';
import { Search, Filter, Calendar, Tag } from 'lucide-react';

interface MemorySearchBarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  dateFrom: string;
  dateTo: string;
  onDateFromChange: (date: string) => void;
  onDateToChange: (date: string) => void;
  selectedTags: string[];
  availableTags: string[];
  onTagToggle: (tag: string) => void;
}

export const MemorySearchBar: React.FC<MemorySearchBarProps> = ({
  searchQuery,
  onSearchChange,
  dateFrom,
  dateTo,
  onDateFromChange,
  onDateToChange,
  selectedTags,
  availableTags,
  onTagToggle,
}) => {
  const [showFilters, setShowFilters] = React.useState(false);

  return (
    <div className="glass rounded-lg p-4 mb-6">
      <div className="flex flex-col gap-4">
        {/* Search Input */}
        <div className="flex gap-2">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 w-5 h-5 text-gray-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => onSearchChange(e.target.value)}
              placeholder="Search memories by content or tags..."
              className="w-full pl-10 pr-4 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-800 dark:text-white"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 ${
              showFilters
                ? 'bg-primary-500 text-white'
                : 'bg-white/50 dark:bg-black/20 text-gray-700 dark:text-gray-300 hover:bg-white/70 dark:hover:bg-black/30'
            }`}
          >
            <Filter className="w-5 h-5" />
            Filters
          </button>
        </div>

        {/* Advanced Filters */}
        {showFilters && (
          <div className="space-y-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            {/* Date Range */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                <Calendar className="w-4 h-4" />
                Date Range
              </label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 mb-1 block">From</label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => onDateFromChange(e.target.value)}
                    className="w-full px-3 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-800 dark:text-white text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 mb-1 block">To</label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => onDateToChange(e.target.value)}
                    className="w-full px-3 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-primary-500 text-gray-800 dark:text-white text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Tags */}
            {availableTags.length > 0 && (
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  <Tag className="w-4 h-4" />
                  Filter by Tags
                </label>
                <div className="flex flex-wrap gap-2">
                  {availableTags.map((tag) => (
                    <button
                      key={tag}
                      onClick={() => onTagToggle(tag)}
                      className={`px-3 py-1 rounded-full text-sm transition-colors ${
                        selectedTags.includes(tag)
                          ? 'bg-primary-500 text-white'
                          : 'bg-white/20 text-gray-700 dark:text-gray-300 hover:bg-white/30'
                      }`}
                    >
                      {tag}
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
