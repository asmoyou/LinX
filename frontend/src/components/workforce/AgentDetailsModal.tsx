import React from 'react';
import { X, Activity, Clock, CheckCircle, MessageSquare } from 'lucide-react';
import type { Agent } from '@/types/agent';

interface AgentDetailsModalProps {
  agent: Agent | null;
  isOpen: boolean;
  onClose: () => void;
  onTest?: (agent: Agent) => void;
}

export const AgentDetailsModal: React.FC<AgentDetailsModalProps> = ({ agent, isOpen, onClose, onTest }) => {
  if (!isOpen || !agent) return null;

  const mockLogs = [
    { timestamp: '2026-01-21 17:05:23', level: 'INFO', message: 'Task execution started' },
    { timestamp: '2026-01-21 17:05:25', level: 'INFO', message: 'Processing data...' },
    { timestamp: '2026-01-21 17:05:30', level: 'SUCCESS', message: 'Task completed successfully' },
    { timestamp: '2026-01-21 17:05:31', level: 'INFO', message: 'Waiting for next task' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm overflow-auto" style={{ marginLeft: 'var(--sidebar-width, 0px)' }}>
      <div className="w-full max-w-4xl my-auto max-h-[90vh] overflow-y-auto bg-white dark:bg-zinc-900 rounded-3xl shadow-2xl p-6">
        <div className="flex items-center justify-between mb-6">
          <h2 className="text-2xl font-bold text-gray-800 dark:text-white">{agent.name}</h2>
          <div className="flex items-center gap-2">
            {onTest && (
              <button
                onClick={() => onTest(agent)}
                className="px-4 py-2 bg-emerald-500 hover:bg-emerald-600 text-white rounded-lg font-semibold transition-colors flex items-center gap-2"
              >
                <MessageSquare className="w-4 h-4" />
                Test Agent
              </button>
            )}
            <button
              onClick={onClose}
              className="p-2 hover:bg-white/20 rounded-lg transition-colors"
            >
              <X className="w-6 h-6 text-gray-700 dark:text-gray-300" />
            </button>
          </div>
        </div>

        {/* Agent Info */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-6">
          <div className="p-4 bg-white/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Activity className="w-5 h-5 text-indigo-500" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Status</span>
            </div>
            <p className="text-lg font-semibold text-gray-800 dark:text-white capitalize">
              {agent.status}
            </p>
          </div>
          <div className="p-4 bg-white/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <CheckCircle className="w-5 h-5 text-green-500" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Tasks Completed</span>
            </div>
            <p className="text-lg font-semibold text-gray-800 dark:text-white">
              {agent.tasksCompleted}
            </p>
          </div>
          <div className="p-4 bg-white/10 rounded-lg">
            <div className="flex items-center gap-2 mb-2">
              <Clock className="w-5 h-5 text-blue-500" />
              <span className="text-sm text-gray-600 dark:text-gray-400">Uptime</span>
            </div>
            <p className="text-lg font-semibold text-gray-800 dark:text-white">{agent.uptime}</p>
          </div>
        </div>

        {/* Current Task */}
        {agent.currentTask && (
          <div className="mb-6">
            <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
              Current Task
            </h3>
            <div className="p-4 bg-white/10 rounded-lg">
              <p className="text-gray-700 dark:text-gray-300">{agent.currentTask}</p>
            </div>
          </div>
        )}

        {/* Logs */}
        <div>
          <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-2">
            Recent Logs
          </h3>
          <div className="bg-black/20 rounded-lg p-4 font-mono text-sm max-h-64 overflow-y-auto">
            {mockLogs.map((log, index) => (
              <div key={index} className="mb-1">
                <span className="text-gray-500">[{log.timestamp}]</span>{' '}
                <span
                  className={
                    log.level === 'SUCCESS'
                      ? 'text-green-400'
                      : log.level === 'ERROR'
                      ? 'text-red-400'
                      : 'text-blue-400'
                  }
                >
                  {log.level}
                </span>{' '}
                <span className="text-gray-300">{log.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};
