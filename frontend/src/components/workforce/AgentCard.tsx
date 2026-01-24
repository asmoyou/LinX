import React from 'react';
import { MoreVertical, Shield, Zap, Eye, Settings, Trash2, MessageSquare } from 'lucide-react';
import type { Agent } from '@/types/agent';
import { useTranslation } from 'react-i18next';

interface AgentCardProps {
  agent: Agent;
  onView: (agent: Agent) => void;
  onConfigure: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
  onTest?: (agent: Agent) => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, onView, onConfigure, onDelete, onTest }) => {
  const { t } = useTranslation();
  const [showMenu, setShowMenu] = React.useState(false);

  const getStatusColor = (status: Agent['status']) => {
    switch (status) {
      case 'working':
        return 'bg-emerald-500';
      case 'idle':
        return 'bg-zinc-400';
      case 'offline':
        return 'bg-red-500';
    }
  };

  // Use agent's avatar if available, otherwise generate a gradient based on name
  const getAvatarDisplay = () => {
    if (agent.avatar) {
      return (
        <img 
          src={agent.avatar} 
          alt={agent.name} 
          className="w-full h-full object-cover"
          onError={(e) => {
            // Fallback to gradient if image fails to load
            e.currentTarget.style.display = 'none';
          }}
        />
      );
    }
    
    // Fallback: Show first letter with gradient background
    return (
      <div className="w-full h-full flex items-center justify-center bg-gradient-to-br from-emerald-400 to-cyan-500">
        <span className="text-3xl font-bold text-white">
          {agent.name.charAt(0).toUpperCase()}
        </span>
      </div>
    );
  };

  const handleTestChat = () => {
    setShowMenu(false);
    if (onTest) {
      onTest(agent);
    }
  };

  return (
    <div className="glass-panel group relative rounded-[32px] overflow-hidden p-8 hover:-translate-y-1 transition-all duration-300">
      <div className="flex justify-between items-start mb-8">
          <div className="relative">
            <div className="w-20 h-20 rounded-[24px] overflow-hidden border-2 border-white dark:border-zinc-800 shadow-2xl">
              {getAvatarDisplay()}
            </div>
            <div className={`absolute -bottom-1 -right-1 w-6 h-6 rounded-full border-4 border-white dark:border-black shadow-lg flex items-center justify-center ${getStatusColor(agent.status)}`}>
              {agent.status === 'working' && <Zap className="w-3.5 h-3.5 text-white" />}
            </div>
          </div>
          <div className="relative">
            <button 
              onClick={() => setShowMenu(!showMenu)}
              className="p-2.5 hover:bg-zinc-500/5 rounded-full text-zinc-400 transition-colors"
            >
              <MoreVertical className="w-5 h-5" />
            </button>
            
            {showMenu && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setShowMenu(false)}
                />
                <div className="absolute right-0 mt-2 w-48 glass-panel rounded-[16px] shadow-2xl z-50 overflow-hidden p-2">
                  <button
                    onClick={() => {
                      onView(agent);
                      setShowMenu(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-zinc-500/5 rounded-lg transition-colors flex items-center gap-2 text-zinc-700 dark:text-zinc-300"
                  >
                    <Eye className="w-4 h-4" />
                    {t('agent.viewDetails')}
                  </button>
                  <button
                    onClick={() => {
                      onConfigure(agent);
                      setShowMenu(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-zinc-500/5 rounded-lg transition-colors flex items-center gap-2 text-zinc-700 dark:text-zinc-300"
                  >
                    <Settings className="w-4 h-4" />
                    {t('agent.configure')}
                  </button>
                  <button
                    onClick={handleTestChat}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-emerald-500/5 rounded-lg transition-colors flex items-center gap-2 text-emerald-600 dark:text-emerald-500"
                  >
                    <MessageSquare className="w-4 h-4" />
                    {t('agent.testAgent')}
                  </button>
                  <button
                    onClick={() => {
                      onDelete(agent);
                      setShowMenu(false);
                    }}
                    className="w-full px-4 py-2 text-left text-sm hover:bg-red-500/5 rounded-lg transition-colors flex items-center gap-2 text-red-500"
                  >
                    <Trash2 className="w-4 h-4" />
                    {t('agent.deleteAgent')}
                  </button>
                </div>
              </>
            )}
          </div>
        </div>

      <div className="space-y-4">
          <div>
            <h3 className="text-2xl font-bold tracking-tight mb-1 text-zinc-800 dark:text-zinc-200">{agent.name}</h3>
            <div className="flex items-center gap-2">
              <Shield className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-500" />
              <span className="text-[10px] font-bold uppercase tracking-[0.2em] text-emerald-600 dark:text-emerald-500">
                {agent.type}
              </span>
            </div>
          </div>
          
          {agent.currentTask && (
            <p className="text-zinc-600 dark:text-zinc-400 text-sm leading-relaxed line-clamp-2">
              {agent.currentTask}
            </p>
          )}
          
          <div className="flex flex-wrap gap-2 pt-2">
            <span className="px-3 py-1.5 bg-zinc-500/5 rounded-lg text-[10px] font-bold text-zinc-700 dark:text-zinc-300 uppercase tracking-tight border border-zinc-500/5">
              {agent.tasksCompleted} Tasks
            </span>
            <span className="px-3 py-1.5 bg-zinc-500/5 rounded-lg text-[10px] font-bold text-zinc-700 dark:text-zinc-300 uppercase tracking-tight border border-zinc-500/5">
              {agent.uptime}
            </span>
            {agent.model && (
              <span className="px-3 py-1.5 bg-emerald-500/10 rounded-lg text-[10px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-tight border border-emerald-500/20">
                {agent.model}
              </span>
            )}
          </div>
      </div>

      <div className="mt-8 pt-6 border-t border-zinc-500/5 flex justify-between items-center">
          <span className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">
            {agent.skills?.length || 0} Skills
          </span>
          <button 
            onClick={handleTestChat}
            className="text-xs font-bold text-emerald-600 hover:text-emerald-500 transition-colors uppercase tracking-widest"
          >
            {t('agent.testAgent')}
          </button>
      </div>
    </div>
  );
};
