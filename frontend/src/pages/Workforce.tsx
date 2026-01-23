import React, { useState, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Plus, Search, Filter, Loader2 } from 'lucide-react';
import type { Agent } from '@/types/agent';
import { AgentCard } from '@/components/workforce/AgentCard';
import { AddAgentModal } from '@/components/workforce/AddAgentModal';
import { AgentDetailsModal } from '@/components/workforce/AgentDetailsModal';
import { AgentConfigModal } from '@/components/workforce/AgentConfigModal';
import { TestAgentModal } from '@/components/workforce/TestAgentModal';
import { agentsApi } from '@/api';
import { useNotificationStore } from '@/stores';

export const Workforce: React.FC = () => {
  const { t } = useTranslation();
  const { addNotification } = useNotificationStore();

  const [agents, setAgents] = useState<Agent[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [searchQuery, setSearchQuery] = useState('');
  const [isAddModalOpen, setIsAddModalOpen] = useState(false);
  const [selectedAgent, setSelectedAgent] = useState<Agent | null>(null);
  const [isDetailsModalOpen, setIsDetailsModalOpen] = useState(false);
  const [isConfigModalOpen, setIsConfigModalOpen] = useState(false);
  const [isTestModalOpen, setIsTestModalOpen] = useState(false);

  // Load agents on mount
  useEffect(() => {
    loadAgents();
  }, []);

  const loadAgents = async () => {
    try {
      setIsLoading(true);
      const data = await agentsApi.getAll();
      setAgents(data);
    } catch (error) {
      console.error('Failed to load agents:', error);
      addNotification({
        type: 'error',
        title: 'Failed to load agents',
        message: 'Could not fetch agents from server',
      });
    } finally {
      setIsLoading(false);
    }
  };

  // Filter agents
  const filteredAgents = agents.filter((agent) => {
    const matchesSearch = agent.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
                         agent.type.toLowerCase().includes(searchQuery.toLowerCase());
    return matchesSearch;
  });

  const handleAddAgent = async (name: string, template: string) => {
    try {
      const newAgent = await agentsApi.create({
        name,
        type: template,
        capabilities: [],
        config: {},
      });
      
      setAgents([...agents, newAgent]);
      
      addNotification({
        type: 'success',
        title: 'Agent created',
        message: `${name} has been created successfully`,
      });
    } catch (error) {
      console.error('Failed to create agent:', error);
      addNotification({
        type: 'error',
        title: 'Failed to create agent',
        message: 'Could not create agent. Please try again.',
      });
    }
  };

  const handleViewAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsDetailsModalOpen(true);
  };

  const handleTestAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsTestModalOpen(true);
  };

  const handleConfigureAgent = (agent: Agent) => {
    setSelectedAgent(agent);
    setIsConfigModalOpen(true);
  };

  const handleSaveConfig = async (updatedAgent: Agent) => {
    try {
      const saved = await agentsApi.update(updatedAgent.id, {
        name: updatedAgent.name,
        capabilities: updatedAgent.skills,
        config: {
          systemPrompt: updatedAgent.systemPrompt,
          model: updatedAgent.model,
          provider: updatedAgent.provider,
          temperature: updatedAgent.temperature,
          maxTokens: updatedAgent.maxTokens,
          topP: updatedAgent.topP,
          accessLevel: updatedAgent.accessLevel,
          allowedKnowledge: updatedAgent.allowedKnowledge,
          allowedMemory: updatedAgent.allowedMemory,
        },
      });
      
      setAgents(agents.map(a => a.id === saved.id ? saved : a));
      
      addNotification({
        type: 'success',
        title: 'Agent updated',
        message: `${saved.name} has been updated successfully`,
      });
    } catch (error) {
      console.error('Failed to update agent:', error);
      addNotification({
        type: 'error',
        title: 'Failed to update agent',
        message: 'Could not update agent. Please try again.',
      });
    }
  };

  const handleDeleteAgent = async (agent: Agent) => {
    if (!confirm(t('agent.deleteConfirm'))) {
      return;
    }
    
    try {
      await agentsApi.delete(agent.id);
      setAgents(agents.filter((a) => a.id !== agent.id));
      
      addNotification({
        type: 'success',
        title: 'Agent deleted',
        message: `${agent.name} has been deleted successfully`,
      });
    } catch (error) {
      console.error('Failed to delete agent:', error);
      addNotification({
        type: 'error',
        title: 'Failed to delete agent',
        message: 'Could not delete agent. Please try again.',
      });
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

      {/* Loading State */}
      {isLoading && (
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-emerald-500" />
          <span className="ml-3 text-zinc-600 dark:text-zinc-400">Loading agents...</span>
        </div>
      )}

      {/* Agent Grid */}
      {!isLoading && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-8">
          {filteredAgents.length === 0 ? (
            <div className="col-span-full text-center py-12">
              <p className="text-zinc-500 dark:text-zinc-400">
                {searchQuery ? 'No agents found matching your search' : 'No agents yet. Create your first agent to get started!'}
              </p>
            </div>
          ) : (
            filteredAgents.map((agent) => (
              <AgentCard
                key={agent.id}
                agent={agent}
                onView={handleViewAgent}
                onConfigure={handleConfigureAgent}
                onDelete={handleDeleteAgent}
                onTest={handleTestAgent}
              />
            ))
          )}
        </div>
      )}

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
        onTest={handleTestAgent}
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
      <TestAgentModal
        agent={selectedAgent}
        isOpen={isTestModalOpen}
        onClose={() => {
          setIsTestModalOpen(false);
          setSelectedAgent(null);
        }}
      />
    </div>
  );
};
