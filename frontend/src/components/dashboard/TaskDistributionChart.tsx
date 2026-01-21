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

interface TaskDistributionChartProps {
  data: Array<{
    name: string;
    tasks: number;
  }>;
}

export const TaskDistributionChart: React.FC<TaskDistributionChartProps> = ({ data }) => {
  return (
    <div className="glass-panel p-8 rounded-[32px]">
      <h3 className="text-sm font-bold uppercase tracking-widest text-zinc-400 mb-8">
        Task Distribution
      </h3>
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
            <XAxis 
              dataKey="name" 
              stroke="#a1a1aa" 
              fontSize={10} 
              tickLine={false} 
              axisLine={false} 
              dy={10} 
            />
            <YAxis 
              stroke="#a1a1aa" 
              fontSize={10} 
              tickLine={false} 
              axisLine={false} 
              dx={-10} 
            />
            <Tooltip 
              contentStyle={{ 
                backgroundColor: 'var(--bg-secondary)', 
                border: '1px solid var(--border-subtle)', 
                borderRadius: '16px', 
                backdropFilter: 'blur(20px)', 
                padding: '12px', 
                fontSize: '12px' 
              }}
              itemStyle={{ color: '#10b981', fontWeight: '600' }}
              cursor={{ stroke: '#10b981', strokeWidth: 1, strokeDasharray: '4 4' }}
            />
            <Area 
              type="monotone" 
              dataKey="tasks" 
              stroke="#10b981" 
              strokeWidth={3} 
              fillOpacity={1} 
              fill="url(#colorTasks)" 
            />
          </AreaChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
};
