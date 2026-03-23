import React from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Filter, Calendar, Tag, Layers, BarChart3 } from 'lucide-react';

const FACT_KIND_OPTIONS = [
  { value: 'preference', labelKey: 'memory.factKind.preference', defaultLabel: 'Preference' },
  { value: 'attribute', labelKey: 'memory.factKind.attribute', defaultLabel: 'Attribute' },
  { value: 'event', labelKey: 'memory.factKind.event', defaultLabel: 'Event' },
  { value: 'relationship', labelKey: 'memory.factKind.relationship', defaultLabel: 'Relationship' },
  { value: 'opinion', labelKey: 'memory.factKind.opinion', defaultLabel: 'Opinion' },
  { value: 'goal', labelKey: 'memory.factKind.goal', defaultLabel: 'Goal' },
];

const RECORD_TYPE_OPTIONS = [
  { value: '', labelKey: 'memory.recordType.all', defaultLabel: 'All' },
  { value: 'user_fact', labelKey: 'memory.recordType.userFact', defaultLabel: 'Facts' },
  { value: 'user_profile', labelKey: 'memory.recordType.userProfile', defaultLabel: 'Profile' },
  { value: 'episode', labelKey: 'memory.recordType.episode', defaultLabel: 'Episodes' },
];

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
  selectedFactKinds: string[];
  onFactKindToggle: (kind: string) => void;
  selectedRecordType: string;
  onRecordTypeChange: (type: string) => void;
  importanceMin: string;
  importanceMax: string;
  onImportanceMinChange: (val: string) => void;
  onImportanceMaxChange: (val: string) => void;
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
  selectedFactKinds,
  onFactKindToggle,
  selectedRecordType,
  onRecordTypeChange,
  importanceMin,
  importanceMax,
  onImportanceMinChange,
  onImportanceMaxChange,
}) => {
  const { t } = useTranslation();
  const [showFilters, setShowFilters] = React.useState(false);

  const activeFilterCount = [
    dateFrom,
    dateTo,
    selectedTags.length > 0,
    selectedFactKinds.length > 0,
    selectedRecordType,
    importanceMin,
    importanceMax,
  ].filter(Boolean).length;

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
              placeholder={t('memory.search.placeholder')}
              className="w-full pl-10 pr-4 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white"
            />
          </div>
          <button
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 py-2 rounded-lg transition-colors flex items-center gap-2 ${
              showFilters
                ? 'bg-indigo-500 text-white'
                : 'bg-white/50 dark:bg-black/20 text-gray-700 dark:text-gray-300 hover:bg-white/70 dark:hover:bg-black/30'
            }`}
          >
            <Filter className="w-5 h-5" />
            {t('common.filter')}
            {activeFilterCount > 0 && (
              <span className="ml-1 inline-flex h-5 w-5 items-center justify-center rounded-full bg-indigo-600 text-xs text-white">
                {activeFilterCount}
              </span>
            )}
          </button>
        </div>

        {/* Advanced Filters */}
        {showFilters && (
          <div className="space-y-4 pt-4 border-t border-gray-200 dark:border-gray-700">
            {/* Date Range */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                <Calendar className="w-4 h-4" />
                {t('memory.search.dateRange', { defaultValue: 'Date Range' })}
              </label>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 mb-1 block">{t('memory.search.dateFrom')}</label>
                  <input
                    type="date"
                    value={dateFrom}
                    onChange={(e) => onDateFromChange(e.target.value)}
                    className="w-full px-3 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white text-sm"
                  />
                </div>
                <div>
                  <label className="text-xs text-gray-600 dark:text-gray-400 mb-1 block">{t('memory.search.dateTo')}</label>
                  <input
                    type="date"
                    value={dateTo}
                    onChange={(e) => onDateToChange(e.target.value)}
                    className="w-full px-3 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Fact Kind */}
            <div>
              <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                <Layers className="w-4 h-4" />
                {t('memory.search.factKind', { defaultValue: 'Fact Type' })}
              </label>
              <div className="flex flex-wrap gap-2">
                {FACT_KIND_OPTIONS.map((opt) => (
                  <button
                    key={opt.value}
                    onClick={() => onFactKindToggle(opt.value)}
                    className={`px-3 py-1 rounded-full text-sm transition-colors ${
                      selectedFactKinds.includes(opt.value)
                        ? 'bg-indigo-500 text-white'
                        : 'bg-white/20 text-gray-700 dark:text-gray-300 hover:bg-white/30 border border-gray-300 dark:border-gray-600'
                    }`}
                  >
                    {t(opt.labelKey, { defaultValue: opt.defaultLabel })}
                  </button>
                ))}
              </div>
            </div>

            {/* Record Type + Importance — inline row */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Record Type */}
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  <Layers className="w-4 h-4" />
                  {t('memory.search.recordType', { defaultValue: 'Record Type' })}
                </label>
                <select
                  value={selectedRecordType}
                  onChange={(e) => onRecordTypeChange(e.target.value)}
                  className="w-full px-3 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white text-sm"
                >
                  {RECORD_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {t(opt.labelKey, { defaultValue: opt.defaultLabel })}
                    </option>
                  ))}
                </select>
              </div>

              {/* Importance Range */}
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  <BarChart3 className="w-4 h-4" />
                  {t('memory.search.importance', { defaultValue: 'Importance' })}
                </label>
                <div className="flex items-center gap-2">
                  <input
                    type="number"
                    value={importanceMin}
                    onChange={(e) => onImportanceMinChange(e.target.value)}
                    placeholder="0.0"
                    min="0"
                    max="1"
                    step="0.1"
                    className="w-24 px-3 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white text-sm"
                  />
                  <span className="text-gray-500 text-sm">—</span>
                  <input
                    type="number"
                    value={importanceMax}
                    onChange={(e) => onImportanceMaxChange(e.target.value)}
                    placeholder="1.0"
                    min="0"
                    max="1"
                    step="0.1"
                    className="w-24 px-3 py-2 bg-white/50 dark:bg-black/20 border border-gray-300 dark:border-gray-600 rounded-lg focus:outline-none focus:ring-2 focus:ring-indigo-500 text-gray-800 dark:text-white text-sm"
                  />
                </div>
              </div>
            </div>

            {/* Tags */}
            {availableTags.length > 0 && (
              <div>
                <label className="flex items-center gap-2 text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                  <Tag className="w-4 h-4" />
                  {t('memory.search.tags')}
                </label>
                <div className="flex flex-wrap gap-2">
                  {availableTags.map((tag) => (
                    <button
                      key={tag}
                      onClick={() => onTagToggle(tag)}
                      className={`px-3 py-1 rounded-full text-sm transition-colors ${
                        selectedTags.includes(tag)
                          ? 'bg-indigo-500 text-white'
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
