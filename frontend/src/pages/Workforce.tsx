import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Search, Filter } from 'lucide-react';
import type { Agent } from '@/types/agent';
import { AgentCard } from '@/components/workforce/AgentCard';
import { AddAgentModal } from '@/components/workforce/AddAgentModal';
import { AgentDetailsModal } from '@/components/workforce/AgentDetailsModal';

export const Workforce: React.FC = () => {
  const { t } = useTranslation();

  // Mock data
  const [agents, setAgents] = useState<Agent[]>([
    {
      id: '1',
      name: 'Analyst-Prime',
      type: 'Data Analyst',
      status: 'idle',
      currentTask: undefined,
      tasksCompleted: 45,
      uptime: '12h 34m',
    },
    {
      id: '2',
      name: 'Scribe-7',
      type: 'Content Writer',
      status: 'working',
      currentTask: 'Writing Q4 report',
      tasksCompleted: 28,
      uptime: '8h 15m',
    },
    {
      id: '3',
      name: 'Code-Assistant-1',
      type: 'Code Assistant',
      status: 'working',
      currentTask: 'Reviewing pull request #234',
      tasksCompleted: 67,
      uptime: '15h 42m',
    },
    {
      id: '4',
      name: 'Research-Unit-1',
      type: 'Research Assistant',
      status: 'offline',
      tasksCompleted: 12,
      uptime: '0h 0m',
    },
    {
      id: '5',
      name: 'Analyst-Beta',
      type: 'Data Analyst',
      status: 'working',
      currentTask: 'Generating monthly report',
      tasksCompleted: 33,
      uptime: '6h 20m',
    },
    {
      id: '6',
      name: 'Scribe-9',
      type: 'Content Writer',
      status: 'idle',
      tasksCompleted: 19,
      uptime: '4h 10m',
    },
  ]);

  const [searchQuery, setSearchQuery] = useState('');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);

  // Filter agents
  const filteredAgents = agents.filter((agent) => {
    const matchesSearch = agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         agent.type.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
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
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2">
            {t('nav.workforce')}
          </h1>
          <p className="text-zinc-500 dark:text-zinc-400 font-medium">
            Manage and monitor your AI agent workforce
          </p>
        </div>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="bg-emerald-500 hover:bg-emerald-600 text-white dark:text-black px-8 py-3 rounded-full font-bold transition-all flex items-center gap-2 shadow-lg shadow-emerald-500/10 active:scale-95"
        >
          <Plus className="w-5 h-5" />
          Deploy Agent
        </button>
      </div>

      {/* Search Bar */}
      <div className="flex gap-4 items-center bg-zinc-500/5 p-2 rounded-2xl border border-zinc-500/10">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input 
            type="text" 
            placeholder="Search agents by name or type..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent border-none py-3 pl-12 pr-4 focus:ring-0 text-sm placeholder:text-zinc-400"
          />
        </div>
        <button className="flex items-center gap-2 px-5 py-2.5 hover:bg-white/10 rounded-xl transition-all text-sm font-semibold text-zinc-500">
          <Filter className="w-4 h-4" />
          Filter
        </button>
      </div>

      {/* Agent Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
        {filteredAgents.length === 0 ? (
          <div className="col-span-full text-center py-12">
            <p className="text-zinc-500 dark:text-zinc-400">No agents found</p>
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
