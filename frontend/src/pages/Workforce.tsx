import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Search, Filter } from 'lucide-react';
import type { Agent } from '@/types/agent';
import { AgentCard } from '@/components/workforce/AgentCard';
import { AddAgentModal } from '@/components/workforce/AddAgentModal';
import { AgentDetailsModal } from '@/components/workforce/AgentDetailsModal';
import { AgentConfigModal } from '@/components/workforce/AgentConfigModal';

export const Workforce: React.FC = () => {
  const { t } = useTranslation();

  // Mock data - will be replaced with real API calls
  const [agents, setAgents] = useState<Agent[]>([
    {
      id: '1',
      name: 'Analyst-Prime',
      type: 'Data Analyst',
      status: 'idle',
      currentTask: undefined,
      tasksCompleted: 45,
      uptime: '12h 34m',
      systemPrompt: 'You are a data analyst specialized in business intelligence.',
      skills: ['data-analysis', 'visualization'],
      model: 'gpt-4',
      provider: 'openai',
    },
    {
      id: '2',
      name: 'Scribe-7',
      type: 'Content Writer',
      status: 'working',
      currentTask: 'Writing Q4 report',
      tasksCompleted: 28,
      uptime: '8h 15m',
      systemPrompt: 'You are a professional content writer.',
      skills: ['writing', 'editing'],
      model: 'claude-3',
      provider: 'anthropic',
    },
    {
      id: '3',
      name: 'Code-Assistant-1',
      type: 'Code Assistant',
      status: 'working',
      currentTask: 'Reviewing pull request #234',
      tasksCompleted: 67,
      uptime: '15h 42m',
      systemPrompt: 'You are a code assistant helping with software development.',
      skills: ['coding', 'debugging'],
      model: 'llama3',
      provider: 'ollama',
    },
  ]);

  const [searchQuery, setSearchQuery] = useState('');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);

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
      systemPrompt: 'You are a helpful AI assistant.',
      skills: [],
      model: 'gpt-4',
      provider: 'openai',
    };
    setAgents([...agents, newAgent]);
  };

  const handleViewAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsDetailsModalOpen(true);
  };

  const handleConfigureAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsConfigModalOpen(true);
  };

  const handleSaveConfig = (updatedAgent: Agent) => {
    setAgents(agents.map(a => a.id === updatedAgent.id ? updatedAgent : a));
  };

  const handleDeleteAgent = (agent: Agent) => {
    if (confirm(t('agent.deleteConfirm'))) {
      setAgents(agents.filter((a) => a.id !== agent.id));
    }
  };

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
        <div>
          <h1 className="text-4xl font-bold tracking-tight mb-2 text-zinc-800 dark:text-zinc-200">
            {t('agent.title')}
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 font-medium">
            {t('agent.subtitle')}
          </p>
        </div>
        <button
          onClick={() => setIsAddModalOpen(true)}
          className="bg-emerald-500 hover:bg-emerald-600 text-white dark:text-black px-8 py-3 rounded-full font-bold transition-all flex items-center gap-2 shadow-lg shadow-emerald-500/10 active:scale-95"
        >
          <Plus className="w-5 h-5" />
          {t('agent.addAgent')}
        </button>
      </div>

      {/* Search Bar */}
      <div className="flex gap-4 items-center bg-zinc-500/5 p-2 rounded-2xl border border-zinc-500/10">
        <div className="relative flex-1">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
          <input 
            type="text" 
            placeholder={t('common.search') + ' agents by name or type...'}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-transparent border-none py-3 pl-12 pr-4 focus:ring-0 text-sm placeholder:text-zinc-400 text-zinc-800 dark:text-zinc-200"
          />
        </div>
        <button className="flex items-center gap-2 px-5 py-2.5 hover:bg-zinc-500/10 rounded-xl transition-all text-sm font-semibold text-zinc-600 dark:text-zinc-400 hover:text-zinc-900 dark:hover:text-white">
          <Filter className="w-4 h-4" />
          {t('common.filter')}
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
              onConfigure={handleConfigureAgent}
              onDelete={handleDeleteAgent}
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
      <AgentConfigModal
        agent={selectedAgent}
        isOpen={isConfigModalOpen}
        onClose={() => {
          setIsConfigModalOpen(false);
          setSelectedAgent(null);
        }}
        onSave={handleSaveConfig}
      />
    </div>
  );
};
