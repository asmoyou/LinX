
import React, { useState } from 'react';
import { Goal, Agent, TaskStatus, Task } from '../types';
import { geminiService } from '../geminiService';
import { 
  Send, 
  Sparkles, 
  CheckCircle, 
  Clock, 
  User, 
  AlertCircle,
  Loader2
} from 'lucide-react';
import { TranslationType, Language } from '../translations';

interface Props {
  goals: Goal[];
  setGoals: React.Dispatch<React.SetStateAction<Goal[]>>;
  agents: Agent[];
  onLog: (msg: string) => void;
  t: TranslationType['tasks'];
  lang: Language;
}

const TaskManager: React.FC<Props> = ({ goals, setGoals, agents, onLog, t, lang }) => {
  const [newGoal, setNewGoal] = useState('');
  const [isDecomposing, setIsDecomposing] = useState(false);

  const handleSubmitGoal = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newGoal.trim() || isDecomposing) return;
    setIsDecomposing(true);
    onLog(`[AI] ${t.decomposing}: ${newGoal}`);
    try {
      const taskBlueprints = await geminiService.decomposeGoal(newGoal, lang);
      const newTasks: Task[] = taskBlueprints.map((b: any, i: number) => ({
        id: `t-${Date.now()}-${i}`,
        goal: b.goal,
        status: TaskStatus.PENDING,
        assignedTo: agents.find(a => a.type === b.assignedToType)?.id || undefined,
        progress: 0
      }));
      setGoals(prev => [{ id: `g-${Date.now()}`, description: newGoal, status: TaskStatus.IN_PROGRESS, createdAt: new Date().toISOString(), tasks: newTasks }, ...prev]);
      setNewGoal('');
    } catch (err) {
      onLog(`Error: Decomposition failed.`);
    } finally {
      setIsDecomposing(false);
    }
  };

  const getStatusIcon = (status: TaskStatus) => {
    switch (status) {
      case TaskStatus.COMPLETED: return <CheckCircle className="w-5 h-5 text-emerald-500" />;
      case TaskStatus.IN_PROGRESS: return <Loader2 className="w-5 h-5 text-blue-500 animate-spin" />;
      case TaskStatus.FAILED: return <AlertCircle className="w-5 h-5 text-red-500" />;
      default: return <Clock className="w-5 h-5 text-zinc-300 dark:text-zinc-600" />;
    }
  };

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <header>
        <h1 className="text-4xl font-bold tracking-tight mb-2">{t.title}</h1>
        <p className="text-zinc-500 dark:text-zinc-400 font-medium">{t.subtitle}</p>
      </header>

      <form onSubmit={handleSubmitGoal} className="relative group">
        <div className="glass-panel p-3 rounded-[32px] flex items-center transition-all duration-500 focus-within:ring-4 focus-within:ring-emerald-500/10">
          <div className="p-4">
            <Sparkles className="w-7 h-7 text-emerald-500" />
          </div>
          <input 
            type="text" 
            value={newGoal}
            onChange={(e) => setNewGoal(e.target.value)}
            disabled={isDecomposing}
            placeholder={t.inputPlaceholder} 
            className="flex-1 bg-transparent border-none py-6 text-xl focus:ring-0 placeholder:text-zinc-400 font-medium"
          />
          <button 
            type="submit"
            disabled={!newGoal.trim() || isDecomposing}
            className="bg-emerald-500 hover:bg-emerald-600 disabled:bg-zinc-200 dark:disabled:bg-zinc-800 disabled:text-zinc-400 text-white dark:text-black px-10 py-5 rounded-[24px] font-bold flex items-center gap-3 transition-all active:scale-95 shadow-xl shadow-emerald-500/10"
          >
            {isDecomposing ? <Loader2 className="w-6 h-6 animate-spin" /> : <Send className="w-6 h-6" />}
            {t.execute}
          </button>
        </div>
      </form>

      <div className="space-y-8">
        {goals.map((goal) => (
          <div key={goal.id} className="glass-panel rounded-[40px] overflow-hidden">
            <div className="bg-zinc-500/5 p-8 border-b border-zinc-500/5 flex justify-between items-center">
              <div>
                <h3 className="text-2xl font-bold tracking-tight">{goal.description}</h3>
                <p className="text-[10px] font-bold text-zinc-400 mt-2 uppercase tracking-widest">{t.id}: {goal.id.toUpperCase()}</p>
              </div>
              <span className={`px-4 py-1.5 rounded-full text-[10px] font-bold uppercase tracking-widest ${
                goal.status === TaskStatus.COMPLETED ? 'bg-emerald-500/10 text-emerald-600' : 'bg-blue-500/10 text-blue-600'
              }`}>
                {goal.status}
              </span>
            </div>
            
            <div className="p-8">
              <div className="space-y-6">
                {goal.tasks.map((task, idx) => {
                  const agent = agents.find(a => a.id === task.assignedTo);
                  return (
                    <div key={task.id} className="flex gap-6 items-start relative group">
                      {idx !== goal.tasks.length - 1 && (
                        <div className="absolute left-[10px] top-8 w-[1.5px] h-[calc(100%+16px)] bg-zinc-500/10"></div>
                      )}
                      <div className="z-10 bg-white dark:bg-black rounded-full p-1 border-4 border-white dark:border-black">
                        {getStatusIcon(task.status)}
                      </div>
                      <div className="flex-1 bg-zinc-500/5 rounded-[24px] p-6 group-hover:bg-zinc-500/10 transition-colors">
                        <div className="flex justify-between items-start mb-4">
                          <h4 className="font-bold text-lg text-zinc-800 dark:text-zinc-200">{task.goal}</h4>
                          <span className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">{task.progress}%</span>
                        </div>
                        <div className="w-full bg-zinc-500/10 h-1.5 rounded-full overflow-hidden mb-6">
                          <div className="bg-emerald-500 h-full transition-all duration-1000" style={{ width: `${task.progress}%` }}></div>
                        </div>
                        <div className="flex justify-between items-center">
                          <div className="flex items-center gap-3">
                            {agent ? (
                              <>
                                <img src={agent.avatar} className="w-7 h-7 rounded-xl border border-white dark:border-zinc-800 shadow-lg" alt="" />
                                <span className="text-xs font-bold text-zinc-500 uppercase tracking-tight">{agent.name}</span>
                              </>
                            ) : (
                              <div className="flex items-center gap-2 text-zinc-400 uppercase tracking-widest text-[10px] font-bold">
                                <User className="w-4 h-4" /> <span>{t.awaiting}</span>
                              </div>
                            )}
                          </div>
                          {task.result && <p className="text-[11px] font-bold text-emerald-600 bg-emerald-500/5 px-4 py-2 rounded-xl border border-emerald-500/10">{t.result}: {task.result}</p>}
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default TaskManager;
