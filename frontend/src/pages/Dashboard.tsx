import React, { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Users, CheckCircle, TrendingUp, Cpu } from 'lucide-react';
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
    { name: 'Completed', value: 45 },
    { name: 'In Progress', value: 25 },
    { name: 'Pending', value: 15 },
    { name: 'Failed', value: 5 },
    { name: 'Queued', value: 10 },
  ]);

  const [events, setEvents] = useState([
    {
      id: '1',
      type: 'success' as const,
      message: 'Agent "Data Analyst #3" completed task successfully',
      timestamp: '2 minutes ago',
    },
    {
      id: '2',
      type: 'info' as const,
      message: 'New goal submitted: "Generate monthly report"',
      timestamp: '5 minutes ago',
    },
    {
      id: '3',
      type: 'success' as const,
      message: 'Document processed: "Q4_Financial_Report.pdf"',
      timestamp: '10 minutes ago',
    },
    {
      id: '4',
      type: 'error' as const,
      message: 'Agent "Code Assistant #1" encountered an error',
      timestamp: '15 minutes ago',
    },
  ]);

  // Simulate real-time updates
  useEffect(() => {
    const interval = setInterval(() => {
      // Update stats with small random changes
      setStats((prev) => ({
        activeAgents: prev.activeAgents + Math.floor(Math.random() * 3) - 1,
        goalsCompleted: prev.goalsCompleted + Math.floor(Math.random() * 2),
        throughput: prev.throughput + Math.floor(Math.random() * 10) - 5,
        computeLoad: Math.max(0, Math.min(100, prev.computeLoad + Math.floor(Math.random() * 10) - 5)),
      }));
    }, 5000);

    return () => clearInterval(interval);
  }, []);

  return (
    <div>
      <h1 className="text-3xl font-bold text-gray-800 dark:text-white mb-6">
        {t('nav.dashboard')}
      </h1>

      {/* Stats Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-6">
        <StatCard
          title="Active Agents"
          value={stats.activeAgents}
          icon={Users}
          trend={{ value: 8.2, isPositive: true }}
          color="text-blue-500"
        />
        <StatCard
          title="Goals Completed"
          value={stats.goalsCompleted}
          icon={CheckCircle}
          trend={{ value: 12.5, isPositive: true }}
          color="text-green-500"
        />
        <StatCard
          title="Throughput (tasks/hr)"
          value={stats.throughput}
          icon={TrendingUp}
          trend={{ value: 3.1, isPositive: false }}
          color="text-purple-500"
        />
        <StatCard
          title="Compute Load"
          value={`${stats.computeLoad}%`}
          icon={Cpu}
          color="text-orange-500"
        />
      </div>

      {/* Charts and Events */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <TaskDistributionChart data={taskDistribution} />
        <RecentEvents events={events} />
      </div>
    </div>
  );
};
