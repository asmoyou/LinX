import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Activity, CheckCircle2, Clock, Server } from 'lucide-react';
import { StatCard } from '@/components/dashboard/StatCard';
import { TaskDistributionChart } from '@/components/dashboard/TaskDistributionChart';
import { RecentEvents } from '@/components/dashboard/RecentEvents';

export const Dashboard: React.FC = () => {
  const { t } = useTranslation();
  
  // Mock data - will be replaced with real API calls
  const [stats, setStats] = useState({
    activeAgents: 12,
    goalsCompleted: 48,
    throughput: 156,
    computeLoad: 67,
  });

  const [taskDistribution] = useState([
    { name: 'Mon', tasks: 4 },
    { name: 'Tue', tasks: 12 },
    { name: 'Wed', tasks: 8 },
    { name: 'Thu', tasks: 15 },
    { name: 'Fri', tasks: 10 },
    { name: 'Sat', tasks: 6 },
    { name: 'Sun', tasks: 5 },
  ]);

  const [events, setEvents] = useState([
    {
      id: '1',
      type: 'success' as const,
      message: 'Goal "Q4 Report" decomposed into 5 tasks',
      timestamp: '2m',
    },
    {
      id: '2',
      type: 'success' as const,
      message: 'Agent "Data Analyst #3" completed task',
      timestamp: '15m',
    },
    {
      id: '3',
      type: 'info' as const,
      message: 'System maintenance scheduled',
      timestamp: '1h',
    },
    {
      id: '4',
      type: 'info' as const,
      message: 'Cluster scaled to 8 nodes',
      timestamp: '3h',
    },
  ]);

  // Simulate real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      setStats((prev) => ({
        activeAgents: Math.max(0, prev.activeAgents + Math.floor(Math.random() * 3) - 1),
        goalsCompleted: prev.goalsCompleted + Math.floor(Math.random() * 2),
        throughput: Math.max(0, prev.throughput + Math.floor(Math.random() * 10) - 5),
        computeLoad: Math.max(0, Math.min(100, prev.computeLoad + Math.floor(Math.random() * 10) - 5)),
      }));
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div className="space-y-10 animate-in fade-in slide-in-from-bottom-6 duration-700">
      <header>
        <h1 className="text-4xl font-bold tracking-tight mb-2">
          {t('nav.dashboard')}
        </h1>
        <p className="text-zinc-500 dark:text-zinc-400 font-medium">
          Real-time system overview and performance metrics
        </p>
      </header>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          title="Active Agents"
          value={stats.activeAgents}
          subtitle="7 offline"
          icon={Activity}
          trend={{ value: 12.5, isPositive: true }}
          colorClass="bg-emerald-500 text-emerald-600"
        />
        <StatCard
          title="Goals Completed"
          value={stats.goalsCompleted}
          subtitle="3 in progress"
          icon={CheckCircle2}
          trend={{ value: 12.5, isPositive: true }}
          colorClass="bg-blue-500 text-blue-600"
        />
        <StatCard
          title="Throughput"
          value={`${stats.throughput}/hr`}
          subtitle="88% success rate"
          icon={Clock}
          trend={{ value: 3.1, isPositive: false }}
          colorClass="bg-purple-500 text-purple-600"
        />
        <StatCard
          title="Compute Load"
          value={`${stats.computeLoad}%`}
          subtitle="6/10 clusters"
          icon={Server}
          colorClass="bg-orange-500 text-orange-600"
        />
      </div>

      {/* Charts and Events */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2">
          <TaskDistributionChart data={taskDistribution} />
        </div>
        <RecentEvents events={events} />
      </div>
    </div>
  );
};
