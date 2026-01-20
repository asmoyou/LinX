
import React from 'react';
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from 'recharts';
import { Agent, Goal, AgentStatus, TaskStatus } from '../types';
import { Activity, Clock, Server, CheckCircle2 } from 'lucide-react';
import { TranslationType } from '../translations';

interface Props {
  agents: Agent[];
  goals: Goal[];
  t: TranslationType['dashboard'];
}

const Dashboard: React.FC<Props> = ({ agents, goals, t }) => {
  const activeAgents = agents.filter(a => a.status === AgentStatus.WORKING).length;
  const completedTasks = goals.reduce((acc, g) => acc + g.tasks.filter(t => t.status === TaskStatus.COMPLETED).length, 0);
  const totalTasks = goals.reduce((acc, g) => acc + g.tasks.length, 0);
  
  const data = [
    { name: 'Mon', tasks: 4 }, { name: 'Tue', tasks: 12 }, { name: 'Wed', tasks: 8 },
    { name: 'Thu', tasks: 15 }, { name: 'Fri', tasks: 10 }, { name: 'Sat', tasks: 6 }, { name: 'Sun', tasks: 5 },
  ];

  const StatCard = ({ title, value, sub, icon: Icon, colorClass }: any) => (
    <div className="glass-panel p-6 rounded-[24px] group hover:translate-y-[-2px]">
      <div className="flex justify-between items-start mb-4">
        <div className={`p-2.5 rounded-xl ${colorClass} bg-opacity-10 text-opacity-90`}>
          <Icon className="w-5 h-5" />
        </div>
        <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-500 bg-emerald-500/5 px-2 py-0.5 rounded-full">+12.5%</span>
      </div>
      <div>
        <h3 className="text-3xl font-bold tracking-tight mb-1">{value}</h3>
        <p className="text-zinc-500 dark:text-zinc-400 text-xs font-medium uppercase tracking-wider">{title}</p>
        <p className="text-zinc-400 dark:text-zinc-500 text-[10px] mt-2 font-mono">{sub}</p>
      </div>
    </div>
  );

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <header>
        <h1 className="text-4xl font-bold tracking-tight mb-2">{t.title}</h1>
        <p className="text-zinc-500 dark:text-zinc-400 font-medium">{t.subtitle}</p>
      </header>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard title={t.activeAgents} value={activeAgents} sub={`7 ${t.offline}`} icon={Activity} colorClass="bg-emerald-500 text-emerald-600" />
        <StatCard title={t.goalsCompleted} value={goals.filter(g => g.status === TaskStatus.COMPLETED).length} sub={`3 ${t.inProgress}`} icon={CheckCircle2} colorClass="bg-blue-500 text-blue-600" />
        <StatCard title={t.throughput} value={`${completedTasks}/${totalTasks}`} sub={`88% ${t.successRate}`} icon={Clock} colorClass="bg-purple-500 text-purple-600" />
        <StatCard title={t.computeLoad} value="42%" sub={`6/10 ${t.clusters}`} icon={Server} colorClass="bg-orange-500 text-orange-600" />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 glass-panel p-8 rounded-[32px]">
          <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400 mb-8">{t.distribution}</h3>
          <div className="h-[280px] w-full">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={data}>
                <defs>
                  <linearGradient id="colorTasks" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.1}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(120,120,128,0.08)" vertical={false} />
                <XAxis dataKey="name" stroke="#a1a1aa" fontSize={10} tickLine={false} axisLine={false} dy={10} />
                <YAxis stroke="#a1a1aa" fontSize={10} tickLine={false} axisLine={false} dx={-10} />
                <Tooltip 
                  contentStyle={{ backgroundColor: 'var(--bg-secondary)', border: '1px solid var(--border-subtle)', borderRadius: '16px', backdropFilter: 'blur(20px)', padding: '12px', fontSize: '12px' }}
                  itemStyle={{ color: '#10b981', fontWeight: '600' }}
                  cursor={{ stroke: '#10b981', strokeWidth: 1, strokeDasharray: '4 4' }}
                />
                <Area type="monotone" dataKey="tasks" stroke="#10b981" strokeWidth={3} fillOpacity={1} fill="url(#colorTasks)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="glass-panel p-8 rounded-[32px]">
          <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400 mb-8">{t.recentEvents}</h3>
          <div className="space-y-6">
            {[
              { time: '2m', event: t.events.decomposed },
              { time: '15m', event: t.events.completed },
              { time: '1h', event: t.events.maintenance },
              { time: '3h', event: t.events.scaled },
            ].map((ev, i) => (
              <div key={i} className="flex gap-4 items-start group">
                <div className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 pt-1 w-8 uppercase">{ev.time}</div>
                <div className="flex-1">
                  <div className="text-sm font-semibold text-zinc-700 dark:text-zinc-200 group-hover:text-emerald-500 transition-colors duration-300">{ev.event}</div>
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
};

export default Dashboard;
