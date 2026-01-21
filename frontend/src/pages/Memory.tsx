import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Brain, Building, User } from 'lucide-react';
import { MemoryCard } from '@/components/memory/MemoryCard';
import { MemorySearchBar } from '@/components/memory/MemorySearchBar';
import { MemoryDetailView } from '@/components/memory/MemoryDetailView';
import { MemorySharingModal } from '@/components/memory/MemorySharingModal';
import type { Memory as MemoryType, MemoryType as MemoryCategory } from '@/types/memory';

export const Memory: React.FC = () => {
  const { t } = useTranslation();
  const [activeTab, setActiveTab] = useState<MemoryCategory>('agent');
  const [memories, setMemories] = useState<MemoryType[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [selectedTags, setSelectedTags] = useState<string[]>([]);
  const [selectedMemory, setSelectedMemory] = useState<Memory | null>(null);
  const [isDetailViewOpen, setIsDetailViewOpen] = useState(false);
  const [sharingMemory, setSharingMemory] = useState<Memory | null>(null);
  const [isSharingModalOpen, setIsSharingModalOpen] = useState(false);

  // Mock data for demonstration
  useEffect(() => {
    const mockMemories: Memory[] = [
      {
        id: '1',
        type: 'agent',
        content: 'Successfully completed data analysis task. Identified key trends in Q4 sales data showing 15% growth in enterprise segment.',
        summary: 'Q4 Sales Analysis Complete',
        agentId: 'agent-1',
        agentName: 'Data Analyst #1',
        createdAt: new Date(Date.now() - 3600000).toISOString(),
        tags: ['sales', 'analysis', 'Q4'],
        relevanceScore: 0.95,
        metadata: {
          taskId: 't1',
          goalId: 'g1',
        },
      },
      {
        id: '2',
        type: 'company',
        content: 'Company-wide policy update: All reports must include executive summary and key metrics dashboard.',
        summary: 'Report Format Policy Update',
        userId: 'admin',
        userName: 'Admin',
        createdAt: new Date(Date.now() - 86400000).toISOString(),
        tags: ['policy', 'reporting', 'standards'],
        isShared: true,
        sharedWith: ['All Agents'],
      },
      {
        id: '3',
        type: 'user_context',
        content: 'User prefers detailed technical explanations with code examples. Interested in Python and TypeScript.',
        summary: 'User Communication Preferences',
        userId: 'user-1',
        userName: 'John Doe',
        createdAt: new Date(Date.now() - 172800000).toISOString(),
        tags: ['preferences', 'communication', 'technical'],
      },
      {
        id: '4',
        type: 'agent',
        content: 'Learned new pattern for handling large datasets: Use chunking with 10k records per batch for optimal performance.',
        summary: 'Data Processing Optimization',
        agentId: 'agent-1',
        agentName: 'Data Analyst #1',
        createdAt: new Date(Date.now() - 259200000).toISOString(),
        tags: ['optimization', 'performance', 'data-processing'],
        relevanceScore: 0.87,
      },
      {
        id: '5',
        type: 'company',
        content: 'New security protocol: All confidential documents must be encrypted and access logged.',
        summary: 'Security Protocol Update',
        userId: 'admin',
        userName: 'Admin',
        createdAt: new Date(Date.now() - 345600000).toISOString(),
        tags: ['security', 'compliance', 'policy'],
        isShared: true,
        sharedWith: ['All Agents', 'All Users'],
      },
      {
        id: '6',
        type: 'user_context',
        content: 'User works in Pacific timezone (PST). Prefers morning meetings between 9-11 AM.',
        summary: 'User Schedule Preferences',
        userId: 'user-1',
        userName: 'John Doe',
        createdAt: new Date(Date.now() - 432000000).toISOString(),
        tags: ['schedule', 'timezone', 'preferences'],
      },
    ];
    setMemories(mockMemories);
  }, []);

  // Get all unique tags
  const allTags = Array.from(new Set(memories.flatMap((m) => m.tags)));

  // Filter memories
  const filteredMemories = memories.filter((memory) => {
    // Filter by tab
    if (memory.type !== activeTab) return false;

    // Filter by search query
    if (searchQuery) {
      const query = searchQuery.toLowerCase();
      const matchesContent = memory.content.toLowerCase().includes(query);
      const matchesSummary = memory.summary?.toLowerCase().includes(query);
      const matchesTags = memory.tags.some((tag) => tag.toLowerCase().includes(query));
      if (!matchesContent && !matchesSummary && !matchesTags) return false;
    }

    // Filter by date range
    if (dateFrom && new Date(memory.createdAt) < new Date(dateFrom)) return false;
    if (dateTo && new Date(memory.createdAt) > new Date(dateTo)) return false;

    // Filter by tags
    if (selectedTags.length > 0) {
      if (!selectedTags.some((tag) => memory.tags.includes(tag))) return false;
    }

    return true;
  });

  const handleMemoryClick = (memory: Memory) => {
    setSelectedMemory(memory);
    setIsDetailViewOpen(true);
  };

  const handleShare = (memory: Memory) => {
    setSharingMemory(memory);
    setIsSharingModalOpen(true);
  };

  const handleShareSubmit = (memoryId: string, shareWith: string[]) => {
    // Update memory sharing status
    setMemories((prev) =>
      prev.map((m) =>
        m.id === memoryId
          ? { ...m, isShared: true, sharedWith: shareWith }
          : m
      )
    );
  };

  const handleTagToggle = (tag: string) => {
    setSelectedTags((prev) =>
      prev.includes(tag) ? prev.filter((t) => t !== tag) : [...prev, tag]
    );
  };

  const tabs = [
    { id: 'agent' as MemoryType, label: 'Agent Memory', icon: Brain, color: 'text-blue-500' },
    { id: 'company' as MemoryType, label: 'Company Memory', icon: Building, color: 'text-green-500' },
    { id: 'user_context' as MemoryType, label: 'User Context', icon: User, color: 'text-purple-500' },
  ];

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-6">
        {t('nav.memory')}
      </h1>

      {/* Tabs */}
      <div className="flex gap-2 mb-6 overflow-x-auto">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const count = memories.filter((m) => m.type === tab.id).length;
          return (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`flex items-center gap-2 px-4 py-3 rounded-lg transition-colors whitespace-nowrap ${
                activeTab === tab.id
                  ? 'bg-indigo-500 text-white'
                  : 'glass text-gray-700 dark:text-gray-300 hover:bg-white/30 dark:hover:bg-black/30'
              }`}
            >
              <Icon className={`w-5 h-5 ${activeTab === tab.id ? 'text-white' : tab.color}`} />
              <span className="font-medium">{tab.label}</span>
              <span className={`px-2 py-0.5 rounded-full text-xs ${
                activeTab === tab.id
                  ? 'bg-white/20'
                  : 'bg-black/10 dark:bg-white/10'
              }`}>
                {count}
              </span>
            </button>
          );
        })}
      </div>

      {/* Search Bar */}
      <MemorySearchBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        dateFrom={dateFrom}
        dateTo={dateTo}
        onDateFromChange={setDateFrom}
        onDateToChange={setDateTo}
        selectedTags={selectedTags}
        availableTags={allTags}
        onTagToggle={handleTagToggle}
      />

      {/* Memory Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredMemories.length === 0 ? (
          <div className="col-span-full text-center py-12">
            <p className="text-gray-500 dark:text-gray-400">
              {memories.filter((m) => m.type === activeTab).length === 0
                ? `No ${tabs.find((t) => t.id === activeTab)?.label.toLowerCase()} yet.`
                : 'No memories match your search criteria.'}
            </p>
          </div>
        ) : (
          filteredMemories.map((memory) => (
            <MemoryCard
              key={memory.id}
              memory={memory}
              onClick={handleMemoryClick}
              showRelevance={memory.type === 'agent'}
            />
          ))
        )}
      </div>

      {/* Modals */}
      <MemoryDetailView
        memory={selectedMemory}
        isOpen={isDetailViewOpen}
        onClose={() => {
          setIsDetailViewOpen(false);
          setSelectedMemory(null);
        }}
        onShare={handleShare}
      />
      <MemorySharingModal
        memory={sharingMemory}
        isOpen={isSharingModalOpen}
        onClose={() => {
          setIsSharingModalOpen(false);
          setSharingMemory(null);
        }}
        onShare={handleShareSubmit}
      />
    </div>
  );
};
