import React from "react";
import { MoreVertical, Shield, Zap, Eye, Settings, Trash2 } from "lucide-react";
import type { Agent } from "@/types/agent";
import { useTranslation } from "react-i18next";

interface AgentCardProps {
  agent: Agent;
  onView: (agent: Agent) => void;
  onConfigure: (agent: Agent) => void;
  onDelete: (agent: Agent) => void;
  onStartConversation: (agent: Agent) => void;
}

export const AgentCard: React.FC<AgentCardProps> = ({
  agent,
  onView,
  onConfigure,
  onDelete,
  onStartConversation,
}) => {
  const { t } = useTranslation();
  const [showMenu, setShowMenu] = React.useState(false);
  const tasksExecuted = Math.max(
    0,
    agent.tasksExecuted ??
      (agent.tasksCompleted ?? 0) + (agent.tasksFailed ?? 0),
  );
  const tasksCompleted = Math.max(0, agent.tasksCompleted ?? 0);
  const tasksFailed = Math.max(
    0,
    agent.tasksFailed ?? tasksExecuted - tasksCompleted,
  );
  const rawCompletionRate =
    typeof agent.completionRate === "number"
      ? agent.completionRate > 1
        ? agent.completionRate / 100
        : agent.completionRate
      : tasksExecuted > 0
        ? tasksCompleted / tasksExecuted
        : 0;
  const completionRate = Math.max(0, Math.min(1, rawCompletionRate));
  const completionRateLabel = `${(completionRate * 100).toFixed(tasksExecuted > 0 ? 1 : 0)}%`;
  const boundSkillCount =
    agent.skill_summaries?.length || agent.skill_ids?.length || 0;

  const getStatusColor = (status: Agent["status"]) => {
    switch (status) {
      case "working":
        return "bg-emerald-500";
      case "idle":
        return "bg-zinc-400";
      case "offline":
        return "bg-red-500";
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
            e.currentTarget.style.display = "none";
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

  const handleStartConversation = () => {
    setShowMenu(false);
    onStartConversation(agent);
  };

  return (
    <div className="glass-panel group relative rounded-2xl overflow-hidden p-5 hover:-translate-y-1 transition-all duration-300">
      <div className="flex justify-between items-start mb-4">
        <div className="relative">
          <div className="w-14 h-14 rounded-xl overflow-hidden border-2 border-white dark:border-zinc-800 shadow-lg">
            {getAvatarDisplay()}
          </div>
          <div
            className={`absolute -bottom-0.5 -right-0.5 w-5 h-5 rounded-full border-3 border-white dark:border-black shadow-lg flex items-center justify-center ${getStatusColor(agent.status)}`}
          >
            {agent.status === "working" && (
              <Zap className="w-2.5 h-2.5 text-white" />
            )}
          </div>
        </div>
        <div className="relative">
          <button
            onClick={() => setShowMenu(!showMenu)}
            className="p-1.5 hover:bg-zinc-500/5 rounded-lg text-zinc-400 transition-colors"
          >
            <MoreVertical className="w-4 h-4" />
          </button>

          {showMenu && (
            <>
              <div
                className="fixed inset-0 z-40"
                onClick={() => setShowMenu(false)}
              />
              <div className="absolute right-0 mt-2 w-44 glass-panel rounded-xl shadow-2xl z-50 overflow-hidden p-1.5">
                <button
                  onClick={() => {
                    onView(agent);
                    setShowMenu(false);
                  }}
                  className="w-full px-3 py-2 text-left text-xs hover:bg-zinc-500/5 rounded-lg transition-colors flex items-center gap-2 text-zinc-700 dark:text-zinc-300"
                >
                  <Eye className="w-3.5 h-3.5" />
                  {t("agent.viewDetails")}
                </button>
                <button
                  onClick={() => {
                    onConfigure(agent);
                    setShowMenu(false);
                  }}
                  className="w-full px-3 py-2 text-left text-xs hover:bg-zinc-500/5 rounded-lg transition-colors flex items-center gap-2 text-zinc-700 dark:text-zinc-300"
                >
                  <Settings className="w-3.5 h-3.5" />
                  {t("agent.configure")}
                </button>
                <button
                  onClick={() => {
                    onDelete(agent);
                    setShowMenu(false);
                  }}
                  className="w-full px-3 py-2 text-left text-xs hover:bg-red-500/5 rounded-lg transition-colors flex items-center gap-2 text-red-500"
                >
                  <Trash2 className="w-3.5 h-3.5" />
                  {t("agent.deleteAgent")}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      <div className="space-y-3">
        <div>
          <h3 className="text-lg font-bold tracking-tight mb-0.5 text-zinc-800 dark:text-zinc-200">
            {agent.name}
          </h3>
          <div className="flex items-center gap-1.5">
            <Shield className="w-3 h-3 text-emerald-600 dark:text-emerald-500" />
            <span className="text-[9px] font-bold uppercase tracking-wider text-emerald-600 dark:text-emerald-500">
              {agent.type}
            </span>
          </div>
        </div>

        {agent.currentTask && (
          <p className="text-zinc-600 dark:text-zinc-400 text-xs leading-relaxed line-clamp-2">
            {agent.currentTask}
          </p>
        )}

        <div className="flex flex-wrap gap-1.5">
          <span className="px-2 py-1 bg-zinc-500/5 rounded-md text-[9px] font-bold text-zinc-700 dark:text-zinc-300 uppercase tracking-tight border border-zinc-500/5">
            {tasksExecuted} {t("agent.stats.tasksExecuted", "Tasks")}
          </span>
          <span className="px-2 py-1 bg-zinc-500/5 rounded-md text-[9px] font-bold text-zinc-700 dark:text-zinc-300 uppercase tracking-tight border border-zinc-500/5">
            {t("agent.stats.completionRateShort", "Completion")}{" "}
            {completionRateLabel}
          </span>
          {tasksFailed > 0 && (
            <span className="px-2 py-1 bg-red-500/10 rounded-md text-[9px] font-bold text-red-700 dark:text-red-400 uppercase tracking-tight border border-red-500/20">
              {tasksFailed} {t("agent.stats.failed", "Failed")}
            </span>
          )}
          {agent.model && (
            <span className="px-2 py-1 bg-emerald-500/10 rounded-md text-[9px] font-bold text-emerald-700 dark:text-emerald-400 uppercase tracking-tight border border-emerald-500/20">
              {agent.model}
            </span>
          )}
        </div>
      </div>

      <div className="mt-4 pt-3 border-t border-zinc-500/5 flex justify-between items-center">
        <span className="text-[9px] text-zinc-400 font-bold uppercase tracking-wider">
          {boundSkillCount} Skills
        </span>
        <button
          onClick={handleStartConversation}
          className="text-[10px] font-bold text-emerald-600 hover:text-emerald-500 transition-colors uppercase tracking-wider"
        >
          {t("agent.startConversation", "开启对话")}
        </button>
      </div>
    </div>
  );
};
