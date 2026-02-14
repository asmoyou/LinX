import React from "react";
import { Search, Filter, ShieldCheck, FileType } from "lucide-react";
import { DepartmentSelect } from "@/components/departments/DepartmentSelect";
import { useTranslation } from "react-i18next";

interface SearchBarProps {
  searchQuery: string;
  onSearchChange: (query: string) => void;
  typeFilter: string;
  onTypeFilterChange: (type: string) => void;
  accessFilter: string;
  onAccessFilterChange: (access: string) => void;
  departmentFilter?: string;
  onDepartmentFilterChange?: (departmentId: string | undefined) => void;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  searchQuery,
  onSearchChange,
  typeFilter,
  onTypeFilterChange,
  accessFilter,
  onAccessFilterChange,
  departmentFilter,
  onDepartmentFilterChange,
}) => {
  const { t } = useTranslation();

  return (
    <div className="glass-dark rounded-2xl p-5 mb-8 border border-white/10 shadow-xl shadow-black/5">
      <div className="flex flex-col lg:flex-row gap-4">
        {/* Search Input */}
        <div className="flex-1 relative group">
          <Search className="absolute left-4 top-1/2 transform -translate-y-1/2 w-5 h-5 text-zinc-500 group-focus-within:text-indigo-500 transition-colors" />
          <input
            type="text"
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            placeholder={t("common.searchPlaceholder", "Search documents, tags, or content...")}
            className="w-full pl-12 pr-4 py-3 bg-white/5 dark:bg-zinc-900/50 border border-zinc-300/50 dark:border-zinc-700/50 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/50 focus:border-indigo-500/50 text-gray-800 dark:text-white transition-all placeholder:text-zinc-500 font-medium"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3">
          {/* Type Filter */}
          <div className="relative min-w-[140px]">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
              <FileType className="w-4 h-4 text-zinc-500" />
            </div>
            <select
              value={typeFilter}
              onChange={(e) => onTypeFilterChange(e.target.value)}
              className="w-full pl-10 pr-8 py-3 bg-white/5 dark:bg-zinc-900/50 border border-zinc-300/50 dark:border-zinc-700/50 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-sm font-semibold text-gray-700 dark:text-zinc-200 appearance-none transition-all cursor-pointer hover:bg-white/10 dark:hover:bg-zinc-800/50"
            >
              <option value="all">All Types</option>
              <option value="pdf">PDF</option>
              <option value="docx">DOCX</option>
              <option value="ppt">PPTX</option>
              <option value="excel">Excel</option>
              <option value="txt">TXT</option>
              <option value="md">Markdown</option>
              <option value="image">Images</option>
              <option value="audio">Audio</option>
              <option value="video">Video</option>
            </select>
            <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-500">
              <Filter className="w-3.5 h-3.5" />
            </div>
          </div>

          {/* Access Level Filter */}
          <div className="relative min-w-[160px]">
            <div className="absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none">
              <ShieldCheck className="w-4 h-4 text-zinc-500" />
            </div>
            <select
              value={accessFilter}
              onChange={(e) => onAccessFilterChange(e.target.value)}
              className="w-full pl-10 pr-8 py-3 bg-white/5 dark:bg-zinc-900/50 border border-zinc-300/50 dark:border-zinc-700/50 rounded-xl focus:outline-none focus:ring-2 focus:ring-indigo-500/50 text-sm font-semibold text-gray-700 dark:text-zinc-200 appearance-none transition-all cursor-pointer hover:bg-white/10 dark:hover:bg-zinc-800/50"
            >
              <option value="all">All Access</option>
              <option value="public">Public</option>
              <option value="internal">Internal</option>
              <option value="confidential">Confidential</option>
              <option value="restricted">Restricted</option>
            </select>
            <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-zinc-500">
              <Filter className="w-3.5 h-3.5" />
            </div>
          </div>

          {/* Department Filter */}
          {onDepartmentFilterChange && (
            <div className="min-w-[180px]">
              <DepartmentSelect
                value={departmentFilter}
                onChange={onDepartmentFilterChange}
                showAll
                className="!py-3 !rounded-xl !border-zinc-300/50 dark:!border-zinc-700/50 !bg-white/5 dark:!bg-zinc-900/50 hover:!bg-white/10 dark:hover:!bg-zinc-800/50 transition-all font-semibold text-sm"
              />
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

