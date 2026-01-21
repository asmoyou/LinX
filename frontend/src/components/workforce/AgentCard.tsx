import React from 'react';
import { Activity, Pause, Power, MoreVertical, Eye, Trash2 } from 'lucide-react';
import { GlassPanel } from '@/components/GlassPanel';
import { Agent } from '@/types/agent';

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
        return 'bg-green-500';
      case 'idle':
        return 'bg-yellow-500';
      case 'offline':
        return 'bg-gray-500';
    }
  };

  const getStatusIcon = (status: Agent['status']) => {
    switch (status) {
      case 'working':
        return <Activity className="w-4 h-4" />;
      case 'idle':
        return <Pause className="w-4 h-4" />;
      case 'offline':
        return <Power className="w-4 h-4" />;
    }
  };

  return (
    <GlassPanel className="hover:scale-105 transition-transform duration-200 relative">
      {/* Status Badge */}
      <div className="absolute top-4 right-4">
        <div className={`flex items-center gap-2 px-2 py-1 rounded-full ${getStatusColor(agent.status)} bg-opacity-20`}>
          {getStatusIcon(agent.status)}
          <span className="text-xs font-medium capitalize">{agent.status}</span>
        </div>
      </div>

      {/* Agent Info */}
      <div className="mb-4">
        <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-1">
          {agent.name}
        </h3>
        <p className="text-sm text-gray-600 dark:text-gray-400">{agent.type}</p>
      </div>

      {/* Current Task */}
      {agent.currentTask && (
        <div className="mb-4 p-2 bg-white/10 rounded">
          <p className="text-xs text-gray-500 dark:text-gray-400 mb-1">Current Task</p>
          <p className="text-sm text-gray-700 dark:text-gray-300 truncate">{agent.currentTask}</p>
        </div>
      )}

      {/* Stats */}
      <div className="flex items-center justify-between text-sm mb-4">
        <div>
          <p className="text-gray-500 dark:text-gray-400">Tasks Completed</p>
          <p className="font-semibold text-gray-800 dark:text-white">{agent.tasksCompleted}</p>
        </div>
        <div>
          <p className="text-gray-500 dark:text-gray-400">Uptime</p>
          <p className="font-semibold text-gray-800 dark:text-white">{agent.uptime}</p>
        </div>
      </div>

      {/* Actions */}
      <div className="flex items-center gap-2">
        <button
          onClick={() => onView(agent)}
          className="flex-1 px-3 py-2 bg-primary-500 text-white rounded-lg hover:bg-primary-600 transition-colors text-sm font-medium"
        >
          View Details
        </button>
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="p-2 hover:bg-white/20 rounded-lg transition-colors"
          >
            <MoreVertical className="w-5 h-5 text-gray-700 dark:text-gray-300" />
          </button>
          
          {showMenu && (
            <>
              <div
                className="fixed inset-0 z-10"
                onClick={() => setShowMenu(false)}
              />
              <div className="absolute right-0 mt-2 w-48 glass rounded-lg shadow-lg z-20 overflow-hidden">
                <button
                  onClick={() => {
                    onView(agent);
                    setShowMenu(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2"
                >
                  <Eye className="w-4 h-4" />
                  View Logs
                </button>
                <button
                  onClick={() => {
                    onTerminate(agent);
                    setShowMenu(false);
                  }}
                  className="w-full px-4 py-2 text-left text-sm hover:bg-white/20 transition-colors flex items-center gap-2 text-red-500"
                >
                  <Trash2 className="w-4 h-4" />
                  Terminate
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </GlassPanel>
  );
};
