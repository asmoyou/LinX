import React, { useState, useEffect, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { 
  Plus, 
  Info, 
  Cpu, 
  Activity, 
  Battery, 
  Wifi, 
  Zap, 
  MapPin, 
  Shield, 
  Search, 
  Gamepad2, 
  ListRestart, 
  X, 
  TrendingUp, 
  Thermometer, 
  Eye,
  Lock,
  Crosshair,
  Layers
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import toast from 'react-hot-toast';
import { LayoutModal } from '@/components/LayoutModal';

interface RobotExample {
  id: string;
  name: string;
  model: string;
  type: 'humanoid' | 'quadruped' | 'computer' | 'arm';
  status: 'online' | 'working' | 'charging' | 'offline';
  battery: number;
  signal: 'excellent' | 'good' | 'fair' | 'poor';
  location: string;
  currentTask?: string;
  description: string;
  image: string;
  capabilities: string[];
}

interface TelemetryMetric {
  label: string;
  value: string;
  icon: LucideIcon;
  color: string;
}

interface TelemetryDetail {
  label: string;
  value: string;
  subValue?: string;
  status?: 'normal' | 'warning' | 'critical';
}

const TASK_POOL: Record<RobotExample['type'], string[]> = {
  humanoid: ['区域导引', '视觉采样', '协作搬运', '设备点检', '访客接待'],
  quadruped: ['电力巡检', '自主导航测试', '环境建模', '周界防范', '物资配送'],
  arm: ['高精度装配', '零件抓取', '表面质量检测', '自动涂胶', '3D扫描'],
  computer: ['公文自动盖章', '数据合规审计', '边缘流量监控', '硬件安全扫描'],
};

const ROBOT_TYPE_BY_ID: Record<string, RobotExample['type']> = {
  'h2-01': 'humanoid',
  'a2-01': 'quadruped',
  'arm-01': 'arm',
};

export const Robots: React.FC = () => {
  const { t } = useTranslation();
  const [searchQuery, setSearchQuery] = useState('');
  const [filterType, setFilterType] = useState<string>('all');
  const [selectedRobot, setSelectedRobot] = useState<RobotExample | null>(null);
  const [showTelemetry, setShowTelemetry] = useState(false);
  
  // Simulated dynamic state for tasks
  const [robotTasks, setRobotTasks] = useState<Record<string, string>>({
    'a2-01': '区域巡检',
    'arm-01': '精密抓取'
  });

  useEffect(() => {
    const interval = setInterval(() => {
      setRobotTasks(prev => {
        const next = { ...prev };
        ['a2-01', 'arm-01', 'h2-01'].forEach(id => {
          const robotType = ROBOT_TYPE_BY_ID[id];
          if (!robotType) return;
          if (Math.random() > 0.8) {
            const pool = TASK_POOL[robotType];
            next[id] = pool[Math.floor(Math.random() * pool.length)];
          }
        });
        return next;
      });
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  const robots: RobotExample[] = useMemo(() => [
    {
      id: 'h2-01',
      name: t('robots.examples.unitree_h2.name') + ' #01',
      model: 'Unitree H2',
      type: 'humanoid',
      status: 'online',
      battery: 92,
      signal: 'excellent',
      location: '实验室 A区',
      description: t('robots.examples.unitree_h2.description'),
      image: '/robots/h2.webp',
      capabilities: ['重载搬运', '复杂路径规划', '精密操作']
    },
    {
      id: 'a2-01',
      name: t('robots.examples.unitree_a2.name') + ' #05',
      model: 'Unitree A2',
      type: 'quadruped',
      status: 'working',
      battery: 65,
      signal: 'good',
      location: '仓储 2号库',
      currentTask: robotTasks['a2-01'],
      description: t('robots.examples.unitree_a2.description'),
      image: '/robots/a2.webp',
      capabilities: ['全地形越野', '自主避障', '物资运输']
    },
    {
      id: 'oc-01',
      name: t('robots.examples.openclaw_pc.name'),
      model: 'OC-Station v2',
      type: 'computer',
      status: 'online',
      battery: 100,
      signal: 'excellent',
      location: '行政办公区',
      description: t('robots.examples.openclaw_pc.description'),
      image: '/robots/openclaw.webp',
      capabilities: ['公文自动盖章', '硬件安全审计', '私有云节点']
    },
    {
      id: 'h2-02',
      name: t('robots.examples.unitree_h2.name') + ' #02',
      model: 'Unitree H2',
      type: 'humanoid',
      status: 'charging',
      battery: 15,
      signal: 'excellent',
      location: '充电站 03',
      description: t('robots.examples.unitree_h2.description'),
      image: '/robots/h2.webp',
      capabilities: ['高精度组装', '触觉反馈', '多机协作']
    },
    {
      id: 'a2-02',
      name: t('robots.examples.unitree_a2.name') + ' #08',
      model: 'Unitree A2',
      type: 'quadruped',
      status: 'online',
      battery: 88,
      signal: 'fair',
      location: '园区北门',
      description: t('robots.examples.unitree_a2.description'),
      image: '/robots/a2.webp',
      capabilities: ['夜间安防', '环境监测', '快速部署']
    },
    {
      id: 'arm-01',
      name: '工业精密机械臂 #01',
      model: 'Collaborative Arm X',
      type: 'arm',
      status: 'working',
      battery: 100,
      signal: 'excellent',
      location: '生产流水线',
      currentTask: robotTasks['arm-01'],
      description: '高精度协作式机械臂，具备安全碰撞检测功能。',
      image: '/robots/arm.webp',
      capabilities: ['0.01mm 精度', '力控反馈', '快速更换末端']
    }
  ], [robotTasks, t]);

  const filteredRobots = robots.filter(robot => {
    const matchesSearch = robot.name.toLowerCase().includes(searchQuery.toLowerCase()) || 
                         robot.model.toLowerCase().includes(searchQuery.toLowerCase());
    const matchesType = filterType === 'all' || robot.type === filterType;
    return matchesSearch && matchesType;
  });

  // Get specific telemetry based on robot type
  const getTelemetryConfig = (robot: RobotExample) => {
    const isWorking = robot.status === 'working';
    const cpuLoad = isWorking ? '68.4%' : robot.status === 'charging' ? '18.2%' : '11.6%';
    const systemTemp = isWorking ? '46.8°C' : robot.status === 'charging' ? '34.9°C' : '38.2°C';
    
    const baseMetrics: TelemetryMetric[] = [
      { label: 'CPU 负载', value: cpuLoad, icon: TrendingUp, color: 'text-blue-500' },
      { label: '系统温度', value: systemTemp, icon: Thermometer, color: 'text-orange-500' },
    ];

    let typeMetrics: TelemetryMetric[] = [];
    let technicalDetails: TelemetryDetail[] = [];

    switch (robot.type) {
      case 'humanoid':
        typeMetrics = [
          { label: '平衡指数', value: '0.998', icon: Shield, color: 'text-emerald-500' },
          { label: '视觉刷新', value: '120fps', icon: Eye, color: 'text-purple-500' }
        ];
        technicalDetails = [
          { label: '双足同步率', value: '100%', subValue: '偏差 < 0.2ms' },
          { label: '手部压力反馈', value: '4.2N', subValue: '传感器正常' },
          { label: 'IMU 偏航角', value: '0.02°', subValue: '姿态稳定' },
          { label: 'SLAM 建图', value: '已对齐', subValue: '实验室 A区' }
        ];
        break;
      case 'quadruped':
        typeMetrics = [
          { label: '当前步态', value: isWorking ? 'Trot' : 'Stand', icon: Activity, color: 'text-amber-500' },
          { label: '电机扭矩', value: '24.5Nm', icon: Zap, color: 'text-emerald-500' }
        ];
        technicalDetails = [
          { label: '足端压力', value: 'FL: 42N / FR: 41N', subValue: '分布均匀' },
          { label: '地形倾角', value: '1.2°', subValue: '平坦' },
          { label: '雷达云点数', value: '240k/s', subValue: '360° 覆盖' },
          { label: '避障预警', value: '无', subValue: '探测距离 5m' }
        ];
        break;
      case 'arm':
        typeMetrics = [
          { label: '末端坐标', value: 'X:-24.2', icon: Crosshair, color: 'text-rose-500' },
          { label: '负载比例', value: '45%', icon: Layers, color: 'text-indigo-500' }
        ];
        technicalDetails = [
          { label: '重复定位精度', value: '±0.01mm', subValue: '标定有效' },
          { label: '末端工具 (EOAT)', value: '真空吸盘', subValue: '气压正常' },
          { label: '碰撞灵敏度', value: 'Level 8', subValue: '安全等级高' },
          { label: '节拍时间', value: '4.2s', subValue: '符合生产标准' }
        ];
        break;
      case 'computer':
        typeMetrics = [
          { label: '加密吞吐', value: '4.2GB/s', icon: Lock, color: 'text-emerald-500' },
          { label: '硬件节点', value: 'Active', icon: Cpu, color: 'text-blue-500' }
        ];
        technicalDetails = [
          { label: 'HSM 状态', value: '已就绪', subValue: '密钥周期内' },
          { label: 'I/O 带宽', value: '42.5Gbps', subValue: '峰值利用 12%' },
          { label: '物理防拆检测', value: '正常', subValue: '未触发' },
          { label: '安全审计日志', value: '已加密', subValue: '同步至 Cloud' }
        ];
        break;
    }

    return { metrics: [...baseMetrics, ...typeMetrics], details: technicalDetails };
  };

  const handleAddRobot = () => {
    toast((t) => (
      <div className="flex flex-col gap-2">
        <div className="font-bold flex items-center gap-2">
          <Info className="w-4 h-4 text-emerald-500" />
          <span>功能演示</span>
        </div>
        <p className="text-sm">
          该页面目前仅做展示。真实机器人接入需要配置底层驱动协议、私有网络隧道及数字孪生模型。
        </p>
        <button
          onClick={() => toast.dismiss(t.id)}
          className="bg-emerald-500 text-white text-xs py-1 px-3 rounded-full mt-2 self-end font-bold"
        >
          确认
        </button>
      </div>
    ), {
      duration: 6000,
      position: 'top-center',
    });
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'online': return 'bg-emerald-500';
      case 'working': return 'bg-amber-500';
      case 'charging': return 'bg-blue-500';
      case 'offline': return 'bg-zinc-500';
      default: return 'bg-zinc-500';
    }
  };

  const getBatteryColor = (level: number) => {
    if (level > 60) return 'text-emerald-500';
    if (level > 20) return 'text-amber-500';
    return 'text-rose-500';
  };

  const telemetryConfig = useMemo(() => {
    if (!selectedRobot) return { metrics: [], details: [] };
    return getTelemetryConfig(selectedRobot);
  }, [selectedRobot]);

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-6 duration-700">
      {/* Header Section */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-6">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] font-bold uppercase tracking-wider">
              Workforce v2.2
            </span>
            <span className="w-1 h-1 rounded-full bg-zinc-300 dark:bg-zinc-700" />
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">物理实体管理</span>
          </div>
          <h1 className="text-3xl font-bold tracking-tight text-zinc-800 dark:text-zinc-200">
            {t('robots.title')}
          </h1>
        </div>
        <button
          onClick={handleAddRobot}
          className="bg-emerald-500 hover:bg-emerald-600 text-white dark:text-black px-6 py-2.5 rounded-xl font-bold transition-all flex items-center gap-2 shadow-lg shadow-emerald-500/10 active:scale-95 text-sm"
        >
          <Plus className="w-4 h-4" />
          {t('robots.addRobot')}
        </button>
      </div>

      {/* Stats Bar */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        {[
          { label: '在线实体', value: robots.filter(r => r.status !== 'offline').length, icon: Cpu },
          { label: '执行中任务', value: robots.filter(r => r.status === 'working').length, icon: Activity },
          { label: '低电量警报', value: robots.filter(r => r.battery < 20).length, icon: Battery, color: 'text-rose-500' },
          { label: '平均信号', value: '优秀', icon: Wifi, color: 'text-emerald-500' },
        ].map((stat, i) => (
          <div key={i} className="bg-zinc-500/5 rounded-2xl p-4 border border-zinc-500/10 flex items-center gap-4">
            <div className={`p-2 rounded-xl bg-white dark:bg-zinc-800 shadow-sm ${stat.color || 'text-zinc-500'}`}>
              <stat.icon className="w-5 h-5" />
            </div>
            <div>
              <p className="text-[10px] font-bold text-zinc-500 uppercase tracking-wider">{stat.label}</p>
              <p className="text-lg font-bold text-zinc-800 dark:text-zinc-200">{stat.value}</p>
            </div>
          </div>
        ))}
      </div>

      {/* Search & Filter */}
      <div className="flex flex-col md:flex-row gap-4">
        <div className="relative flex-1 group">
          <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400 group-focus-within:text-emerald-500 transition-colors" />
          <input 
            type="text" 
            placeholder="搜索机器人名称、型号..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full bg-zinc-500/5 border border-zinc-500/10 py-3 pl-12 pr-4 rounded-2xl focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500/30 text-sm placeholder:text-zinc-400 text-zinc-800 dark:text-zinc-200 transition-all outline-none"
          />
        </div>
        <div className="flex gap-2 bg-zinc-500/5 p-1 rounded-2xl border border-zinc-500/10">
          {['all', 'humanoid', 'quadruped', 'arm', 'computer'].map((type) => (
            <button
              key={type}
              onClick={() => setFilterType(type)}
              className={`px-4 py-2 rounded-xl text-xs font-bold capitalize transition-all ${
                filterType === type 
                  ? 'bg-white dark:bg-zinc-800 text-emerald-600 dark:text-emerald-400 shadow-sm' 
                  : 'text-zinc-500 hover:text-zinc-700 dark:hover:text-zinc-300'
              }`}
            >
              {type === 'all' ? '全部' : t(`robots.types.${type}`)}
            </button>
          ))}
        </div>
      </div>

      {/* Robot Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 2xl:grid-cols-5 gap-6">
        <AnimatePresence mode="popLayout">
          {filteredRobots.map((robot) => (
            <motion.div
              layout
              key={robot.id}
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.2 }}
              className="bg-white dark:bg-zinc-900 rounded-3xl border border-zinc-500/10 hover:border-emerald-500/30 hover:shadow-xl hover:shadow-emerald-500/5 transition-all duration-300 group overflow-hidden flex flex-col"
            >
              {/* Image Preview */}
              <div className="h-40 relative overflow-hidden bg-zinc-100 dark:bg-zinc-800">
                <img 
                  src={robot.image} 
                  alt={robot.name}
                  className="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
                />
                <div className="absolute top-3 left-3">
                  <div className="flex items-center gap-1.5 px-2 py-1 rounded-full bg-black/50 backdrop-blur-md border border-white/10">
                    <div className={`w-1.5 h-1.5 rounded-full ${getStatusColor(robot.status)} animate-pulse`} />
                    <span className="text-[10px] font-bold text-white uppercase tracking-wider">
                      {t(`robots.status.${robot.status}`)}
                    </span>
                  </div>
                </div>
                <div className="absolute bottom-3 right-3">
                  <div className="px-2 py-1 rounded-lg bg-white/90 dark:bg-zinc-900/90 backdrop-blur-md text-[10px] font-black text-zinc-800 dark:text-zinc-200 border border-zinc-500/10">
                    {robot.model}
                  </div>
                </div>
              </div>

              {/* Info Content */}
              <div className="p-5 flex-1 flex flex-col">
                <div className="mb-4">
                  <h3 className="font-bold text-zinc-800 dark:text-zinc-200 group-hover:text-emerald-600 transition-colors truncate">
                    {robot.name}
                  </h3>
                  <div className="flex items-center gap-1.5 text-zinc-500 mt-1">
                    <MapPin className="w-3 h-3" />
                    <span className="text-[11px] font-medium">{robot.location}</span>
                  </div>
                </div>

                {/* Mini Stats */}
                <div className="flex items-center justify-between py-3 border-y border-zinc-500/5 mb-4">
                  <div className="flex items-center gap-2">
                    <Battery className={`w-3.5 h-3.5 ${getBatteryColor(robot.battery)}`} />
                    <span className="text-xs font-bold text-zinc-700 dark:text-zinc-300">{robot.battery}%</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <Wifi className="w-3.5 h-3.5 text-zinc-400" />
                    <span className="text-[10px] font-bold text-zinc-500 uppercase">{robot.signal}</span>
                  </div>
                </div>

                {/* Current Activity */}
                {(robot.status === 'working' || robot.currentTask) && (
                  <div className={`mb-4 p-2 rounded-xl border ${robot.status === 'working' ? 'bg-amber-500/5 border-amber-500/10' : 'bg-zinc-500/5 border-zinc-500/10'}`}>
                    <div className="flex items-center gap-2 mb-1">
                      <Activity className={`w-3 h-3 ${robot.status === 'working' ? 'text-amber-500' : 'text-zinc-400'}`} />
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${robot.status === 'working' ? 'text-amber-600 dark:text-amber-400' : 'text-zinc-500'}`}>
                        {robot.status === 'working' ? '执行任务中' : '待命/背景任务'}
                      </span>
                    </div>
                    <p className="text-[11px] text-zinc-600 dark:text-zinc-400 font-medium truncate">
                      {robot.currentTask || '系统空闲'}
                    </p>
                  </div>
                )}

                {/* Actions */}
                <div className="grid grid-cols-2 gap-2 mt-auto">
                  <button 
                    onClick={() => toast.success(`正在连接 ${robot.name} 的远程控制链路...`)}
                    className="flex items-center justify-center gap-1.5 py-2 rounded-xl bg-zinc-800 dark:bg-zinc-100 text-white dark:text-black text-[11px] font-bold hover:bg-zinc-700 dark:hover:bg-white transition-colors"
                  >
                    <Gamepad2 className="w-3.5 h-3.5" />
                    远程控制
                  </button>
                  <button 
                    onClick={() => {
                      setSelectedRobot(robot);
                      setShowTelemetry(true);
                    }}
                    className="flex items-center justify-center gap-1.5 py-2 rounded-xl bg-zinc-100 dark:bg-zinc-800 text-zinc-600 dark:text-zinc-400 text-[11px] font-bold hover:bg-zinc-200 dark:hover:bg-zinc-700 transition-colors border border-zinc-500/10"
                  >
                    <ListRestart className="w-3.5 h-3.5" />
                    详细数据
                  </button>
                </div>
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>

      {/* Telemetry Modal */}
      <AnimatePresence>
        {showTelemetry && selectedRobot && (
          <LayoutModal
            isOpen={true}
            onClose={() => setShowTelemetry(false)}
            closeOnBackdropClick={true}
            closeOnEscape={true}
            zIndexClassName="z-[100]"
          >
            <div className="relative w-full max-w-2xl max-h-[calc(100vh-var(--app-header-height,4rem)-3rem)] flex flex-col bg-white dark:bg-zinc-900 rounded-[32px] shadow-2xl overflow-hidden border border-zinc-500/10">
              {/* Modal Header */}
              <div className="p-6 border-b border-zinc-500/10 flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className={`w-12 h-12 rounded-2xl flex items-center justify-center bg-emerald-500/10 text-emerald-500`}>
                    <Cpu className="w-6 h-6" />
                  </div>
                  <div>
                    <h2 className="text-xl font-bold text-zinc-800 dark:text-white">{selectedRobot.name}</h2>
                    <p className="text-xs text-zinc-500 uppercase font-bold tracking-widest">{selectedRobot.model} 深度遥测</p>
                  </div>
                </div>
                <button 
                  onClick={() => setShowTelemetry(false)}
                  className="p-2 hover:bg-zinc-100 dark:hover:bg-zinc-800 rounded-xl transition-colors"
                >
                  <X className="w-6 h-6 text-zinc-400" />
                </button>
              </div>

              {/* Modal Content */}
              <div className="p-8 overflow-y-auto flex-1 min-h-0">
                {/* Metrics Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-8">
                  {telemetryConfig.metrics.map((stat, i) => (
                    <div key={i} className="bg-zinc-500/5 rounded-2xl p-4 border border-zinc-500/10">
                      <stat.icon className={`w-4 h-4 mb-2 ${stat.color}`} />
                      <p className="text-[10px] font-bold text-zinc-500 uppercase mb-1">{stat.label}</p>
                      <p className="text-lg font-black text-zinc-800 dark:text-white">{stat.value}</p>
                    </div>
                  ))}
                </div>

                {/* Type Specific Sections */}
                <div className="space-y-6">
                  <div>
                    <h3 className="text-sm font-bold text-zinc-800 dark:text-white mb-4 flex items-center gap-2">
                      <Activity className="w-4 h-4 text-emerald-500" />
                      关键运行数据 (Technical Details)
                    </h3>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      {telemetryConfig.details.map((detail, i) => (
                        <div key={i} className="flex flex-col p-4 rounded-xl bg-zinc-500/5 border border-zinc-500/10">
                          <span className="text-[10px] font-bold text-zinc-400 uppercase mb-1">{detail.label}</span>
                          <div className="flex items-baseline gap-2">
                            <span className="text-sm font-bold text-zinc-800 dark:text-zinc-100">{detail.value}</span>
                            {detail.subValue && (
                              <span className="text-[10px] text-emerald-600 dark:text-emerald-400 font-medium">{detail.subValue}</span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Shared Logic Section */}
                  <div className="p-4 rounded-2xl bg-zinc-800 dark:bg-zinc-100 flex items-center justify-between">
                    <div>
                      <p className="text-[10px] font-bold text-zinc-400 dark:text-zinc-500 uppercase">当前运行状态</p>
                      <p className="text-sm font-bold text-white dark:text-zinc-900">健康度: 100% (Optimal)</p>
                    </div>
                    <div className="flex -space-x-2">
                      {[1, 2, 3].map(i => (
                        <div key={i} className="w-6 h-6 rounded-full border-2 border-zinc-800 dark:border-white bg-zinc-700 dark:bg-zinc-300 flex items-center justify-center">
                          <Zap className="w-3 h-3 text-emerald-500" />
                        </div>
                      ))}
                    </div>
                  </div>

                  <div className="p-4 rounded-2xl bg-emerald-500/5 border border-emerald-500/10">
                    <div className="flex items-center gap-2 mb-2">
                      <Shield className="w-4 h-4 text-emerald-500" />
                      <h3 className="text-xs font-bold text-emerald-600 dark:text-emerald-400">LinX 隔离保护 (Isolation Guard)</h3>
                    </div>
                    <p className="text-[11px] text-zinc-600 dark:text-zinc-400 leading-relaxed">
                      该实体通过 <b>LinX Shield</b> 加密通道连接。所有下发的物理动作指令均经过 Agent 控制层级权限校验。
                      环境感知的视频流已进行本地匿名化处理后再进入 AI 分析链条。
                    </p>
                  </div>
                </div>
              </div>

              {/* Modal Footer */}
              <div className="p-6 bg-zinc-50 dark:bg-zinc-800/50 border-t border-zinc-500/10 flex justify-end">
                <button 
                  onClick={() => setShowTelemetry(false)}
                  className="px-8 py-2.5 rounded-xl bg-zinc-800 dark:bg-zinc-100 text-white dark:text-black font-bold text-sm hover:scale-105 transition-transform"
                >
                  关闭
                </button>
              </div>
            </div>
          </LayoutModal>
        )}
      </AnimatePresence>

      {/* Demo Footer */}
      <div className="bg-emerald-500/5 rounded-3xl p-8 border border-emerald-500/10 relative overflow-hidden group">
        <div className="absolute -right-12 -bottom-12 w-48 h-48 bg-emerald-500/10 rounded-full blur-3xl group-hover:bg-emerald-500/20 transition-all duration-700" />
        <div className="relative flex flex-col md:flex-row items-center justify-between gap-8">
          <div className="flex-1">
            <h3 className="text-xl font-bold text-zinc-800 dark:text-zinc-200 mb-3 flex items-center gap-2">
              <Shield className="w-6 h-6 text-emerald-500" />
              物理机器人安全集成方案
            </h3>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 leading-relaxed max-w-2xl">
              LinX 平台通过专用边缘网关与物理实体机器人连接。我们支持主流的 ROS/ROS2 协议，
              并提供亚秒级的遥测同步与加密控制链路。无论您的设备是在工厂车间还是园区户外，
              LinX 都能实现智能代理对实体劳动力的高效协同与安全调度。
            </p>
          </div>
          <button className="px-8 py-4 rounded-2xl bg-emerald-500 text-white dark:text-black font-black hover:bg-emerald-600 shadow-xl shadow-emerald-500/20 transition-all active:scale-95 whitespace-nowrap">
            立即申请集成咨询
          </button>
        </div>
      </div>
    </div>
  );
};
