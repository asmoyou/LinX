
import React from 'react';
import { Agent, AgentStatus, Goal, TaskStatus } from './types';

export const AGENT_TEMPLATES = [
  {
    type: 'Data Analyst',
    description: 'Expert in statistical analysis, data visualization, and reporting.',
    skills: ['Python', 'SQL', 'D3.js', 'Market Trends'],
    avatar: 'https://picsum.photos/seed/analyst/200'
  },
  {
    type: 'Content Writer',
    description: 'Specializes in technical documentation, creative writing, and SEO.',
    skills: ['Copywriting', 'Markdown', 'Translation', 'Creative Strategy'],
    avatar: 'https://picsum.photos/seed/writer/200'
  },
  {
    type: 'Research Assistant',
    description: 'Excels at gathering information, summarizing papers, and competitive analysis.',
    skills: ['Google Search', 'PDF Analysis', 'Summarization', 'Fact Checking'],
    avatar: 'https://picsum.photos/seed/research/200'
  },
  {
    type: 'Robotic Controller',
    description: 'Interface for future physical robotic units; handles spatial navigation.',
    skills: ['Pathfinding', 'Obstacle Avoidance', 'Physical Manipulation'],
    avatar: 'https://picsum.photos/seed/robot/200'
  }
];

export const INITIAL_AGENTS: Agent[] = [
  {
    id: 'a1',
    name: 'Analyst-Prime',
    type: 'Data Analyst',
    description: 'Core data analysis unit.',
    skills: ['SQL', 'Python'],
    status: AgentStatus.IDLE,
    avatar: 'https://picsum.photos/seed/a1/200'
  },
  {
    id: 'a2',
    name: 'Scribe-7',
    type: 'Content Writer',
    description: 'Primary documentation agent.',
    skills: ['Copywriting'],
    status: AgentStatus.WORKING,
    avatar: 'https://picsum.photos/seed/a2/200'
  }
];

export const INITIAL_GOALS: Goal[] = [
  {
    id: 'g1',
    description: 'Q4 Market Strategy Report',
    status: TaskStatus.IN_PROGRESS,
    createdAt: new Date().toISOString(),
    tasks: [
      {
        id: 't1',
        goal: 'Analyze competitor performance',
        status: TaskStatus.COMPLETED,
        assignedTo: 'a1',
        progress: 100,
        result: 'Competitors show a 15% increase in cloud adoption.'
      },
      {
        id: 't2',
        goal: 'Draft executive summary',
        status: TaskStatus.IN_PROGRESS,
        assignedTo: 'a2',
        progress: 45
      }
    ]
  }
];
