import { useEffect } from 'react';
import { Database, Cpu, HardDrive, Users } from 'lucide-react';
import { GlassPanel } from '../GlassPanel';
import { useUserStore } from '../../stores';
import { usersApi } from '../../api/users';

export const QuotaSection = () => {
  const { quotas, setQuotas, setLoading } = useUserStore();

  useEffect(() => {
    loadQuotas();
  }, []);

  const loadQuotas = async () => {
    setLoading(true);
    try {
      const data = await usersApi.getQuotas();
      setQuotas(data);
    } catch (error) {
      console.error('Failed to load quotas:', error);
    } finally {
      setLoading(false);
    }
  };

  const quotaItems = [
    {
      label: 'Agents',
      icon: Users,
      current: quotas?.currentAgents || 0,
      max: quotas?.maxAgents || 0,
      unit: '',
      color: 'emerald',
    },
    {
      label: 'Storage',
      icon: HardDrive,
      current: quotas?.currentStorageGb || 0,
      max: quotas?.maxStorageGb || 0,
      unit: 'GB',
      color: 'blue',
    },
    {
      label: 'CPU Cores',
      icon: Cpu,
      current: 0, // Not tracked yet
      max: quotas?.maxCpuCores || 0,
      unit: '',
      color: 'purple',
    },
    {
      label: 'Memory',
      icon: Database,
      current: 0, // Not tracked yet
      max: quotas?.maxMemoryGb || 0,
      unit: 'GB',
      color: 'orange',
    },
  ];

  const getPercentage = (current: number, max: number) => {
    if (max === 0) return 0;
    return Math.min((current / max) * 100, 100);
  };

  const getColorClasses = (color: string, percentage: number) => {
    const isWarning = percentage > 80;
    const isDanger = percentage > 95;
    
    if (isDanger) {
      return {
        bg: 'bg-red-500/20',
        bar: 'bg-red-500',
        text: 'text-red-400',
      };
    }
    
    if (isWarning) {
      return {
        bg: 'bg-yellow-500/20',
        bar: 'bg-yellow-500',
        text: 'text-yellow-400',
      };
    }
    
    return {
      bg: `bg-${color}-500/20`,
      bar: `bg-${color}-500`,
      text: `text-${color}-400`,
    };
  };

  return (
    <GlassPanel className="p-6">
      <div className="space-y-6">
        <div>
          <h2 className="text-xl font-semibold text-white">Resource Quotas</h2>
          <p className="text-sm text-gray-400 mt-1">
            Monitor your resource usage and limits
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {quotaItems.map((item) => {
            const Icon = item.icon;
            const percentage = getPercentage(item.current, item.max);
            const colors = getColorClasses(item.color, percentage);
            
            return (
              <div
                key={item.label}
                className="p-4 bg-white/5 rounded-lg border border-white/10"
              >
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center gap-2">
                    <Icon className={`w-5 h-5 ${colors.text}`} />
                    <h3 className="text-white font-medium">{item.label}</h3>
                  </div>
                  <span className="text-sm text-gray-400">
                    {item.current}{item.unit} / {item.max}{item.unit}
                  </span>
                </div>
                
                <div className={`h-2 rounded-full ${colors.bg} overflow-hidden`}>
                  <div
                    className={`h-full ${colors.bar} transition-all duration-300`}
                    style={{ width: `${percentage}%` }}
                  />
                </div>
                
                <p className="text-xs text-gray-500 mt-2">
                  {percentage.toFixed(1)}% used
                </p>
              </div>
            );
          })}
        </div>

        {quotas && (
          <div className="p-4 bg-blue-500/10 border border-blue-500/30 rounded-lg">
            <p className="text-sm text-blue-400">
              <strong>Note:</strong> Contact your administrator to increase your resource quotas.
            </p>
          </div>
        )}
      </div>
    </GlassPanel>
  );
};
