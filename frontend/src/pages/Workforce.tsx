import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus } from 'lucide-react';
import type { Agent } from '@/types/agent';
import { AgentCard } from '@/components/workforce/AgentCard';
import { SearchFilterBar } from '@/components/workforce/SearchFilterBar';
import { AddAgentModal } from '@/components/workforce/AddAgentModal';
import { AgentDetailsModal } from '@/components/workforce/AgentDetailsModal';

export const Workforce: React.FC = () => {
  const { t } = useTranslation();

  // Mock data
  const [agents, setAgents] = useState<Agent[]>([
    {
      id: '1',
      name: 'Data Analyst #1',
      type: 'Data Analyst',
      status: 'working',
      currentTask: 'Analyzing Q4 sales data',
      tasksCompleted: 45,
      uptime: '12h 34m',
    },
    {
      id: '2',
      name: 'Content Writer #1',
      type: 'Content Writer',
      status: 'idle',
      tasksCompleted: 28,
      uptime: '8h 15m',
    },
    {
      id: '3',
      name: 'Code Assistant #1',
      type: 'Code Assistant',
      status: 'working',
      currentTask: 'Reviewing pull request #234',
      tasksCompleted: 67,
      uptime: '15h 42m',
    },
    {
      id: '4',
      name: 'Research Assistant #1',
      type: 'Research Assistant',
      status: 'offline',
      tasksCompleted: 12,
      uptime: '0h 0m',
    },
    {
      id: '5',
      name: 'Data Analyst #2',
      type: 'Data Analyst',
      status: 'working',
      currentTask: 'Generating monthly report',
      tasksCompleted: 33,
      uptime: '6h 20m',
    },
    {
      id: '6',
      name: 'Content Writer #2',
      type: 'Content Writer',
      status: 'idle',
      tasksCompleted: 19,
      uptime: '4h 10m',
    },
  ]);

  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [typeFilter, setTypeFilter] = useState('all');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);

  // Filter agents
  const filteredAgents = agents.filter((agent) => {
    const matchesSearch = agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         agent.type.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesStatus = statusFilter === 'all' || agent.status === statusFilter;
    const matchesType = typeFilter === 'all' || agent.type === typeFilter;
    return matchesSearch && matchesStatus && matchesType;
  });

  const handleAddAgent = (name: string, template: string) => {
    const newAgent: Agent = {
      id: String(agents.length + 1),
      name,
      type: template.split('-').map(w => w.charAt(0).toUpperCase() + w.slice(1)).join(' '),
      status: 'idle',
      tasksCompleted: 0,
      uptime: '0h 0m',
    };
    setAgents([...agents, newAgent]);
  };

  const handleViewAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsDetailsModalOpen(true);
  };

  const handleTerminateAgent = (agent: Agent) => {
    if (confirm(`Are you sure you want to terminate ${agent.name}?`)) {
      setAgents(agents.filter((a) => a.id !== agent.id));
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold text-gray-800 dark:text-white">
          {t('nav.workforce')}
        </h1>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="flex items-center gap-2 px-4 py-2 bg-indigo-500 text-white rounded-lg hover:bg-indigo-600 transition-colors font-medium"
        >
          <Plus className="w-5 h-5" />
          Add Agent
        </button>
      </div>

      <SearchFilterBar
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        statusFilter={statusFilter}
        onStatusFilterChange={setStatusFilter}
        typeFilter={typeFilter}
        onTypeFilterChange={setTypeFilter}
      />

      {/* Agent Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {filteredAgents.length === 0 ? (
          <div className="col-span-full text-center py-12">
            <p className="text-gray-500 dark:text-gray-400">No agents found</p>
          </div>
        ) : (
          filteredAgents.map((agent) => (
            <AgentCard
              key={agent.id}
              agent={agent}
              onView={handleViewAgent}
              onTerminate={handleTerminateAgent}
            />
          ))
        )}
      </div>

      {/* Modals */}
      <AddAgentModal
        isOpen={isAddModalOpen}
        onClose={() => setIsAddModalOpen(false)}
        onAdd={handleAddAgent}
      />
      <AgentDetailsModal
        agent={selectedAgent}
        isOpen={isDetailsModalOpen}
        onClose={() => {
          setIsDetailsModalOpen(false);
          setSelectedAgent(null);
        }}
      />
    </div>
  );
};
