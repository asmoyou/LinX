import React from 'react';
import { MoreVertical, Shield, Zap, Eye, Trash2 } from 'lucide-react';
import type { Agent } from '@/types/agent';

interface AgentCardProps {
  agent: Agent;
  onView: (agent: Agent) => void;
  onTerminate: (agent: Agent) => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({ agent, onView, onTerminate }) => {
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

  // Generate avatar based on agent name
  const avatarUrl = `https://picsum.photos/seed/${agent.id}/200`;

  return (
    <div className="glass-panel group relative rounded-[32px] overflow-hidden p-8 hover:-translate-y-1 transition-all duration-300">
      <div className="flex justify-between items-start mb-8">
        <div className="relative">
          <div className="w-20 h-20 rounded-[24px] overflow-hidden border-2 border-white dark:border-zinc-800 shadow-2xl">
            <img src={avatarUrl} alt={agent.name} className="w-full h-full object-cover" />
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
                  View Details
                </button>
                <button
                  onClick={() => {
                    onTerminate(agent);
                    setShowMenu(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-red-500/5 rounded-lg transition-colors flex items-center gap-2 text-red-500"
                >
                  <Trash2 className="w-4 h-4" />
                  Terminate
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
        </div>
      </div>

      <div className="mt-8 pt-6 border-t border-zinc-500/5 flex justify-between items-center">
        <span className="text-[10px] text-zinc-400 font-bold uppercase tracking-widest">
          Memory: 1.2GB
        </span>
        <button 
          onClick={() => onView(agent)}
          className="text-xs font-bold text-emerald-600 hover:text-emerald-500 transition-colors uppercase tracking-widest"
        >
          View Logs
        </button>
      </div>
    </div>
  );
};
