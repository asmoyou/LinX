import React from 'react';
import { PieChart, Pie, Cell, ResponsiveContainer, Legend, Tooltip } from 'recharts';
import { GlassPanel } from '@/components/GlassPanel';

interface TaskDistributionChartProps {
  data: Array<{
    name: string;
    value: number;
  }>;
}

const COLORS = ['#0ea5e9', '#8b5cf6', '#ec4899', '#f59e0b', '#10b981'];

export const TaskDistributionChart: React.FC<TaskDistributionChartProps> = ({ data }) => {
  return (
    <GlassPanel>
      <h3 className="text-lg font-semibold text-gray-800 dark:text-white mb-4">
        Task Distribution
      </h3>
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            labelLine={false}
            label={({ name, percent }) => `${name}: ${(percent * 100).toFixed(0)}%`}
            outerRadius={80}
            fill="#8884d8"
            dataKey="value"
          >
            {data.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
            ))}
          </Pie>
          <Tooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </GlassPanel>
  );
};
