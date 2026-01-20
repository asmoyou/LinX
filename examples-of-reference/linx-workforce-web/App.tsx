
import React, { useState, useEffect } from 'react';
import { 
  Users, 
  LayoutDashboard, 
  Target, 
  Database, 
  BrainCircuit, 
  Settings, 
  Menu, 
  X,
  Bell,
  Search,
  Plus,
  Cpu,
  ShieldCheck,
  Sun,
  Moon,
  Monitor
} from 'lucide-react';
import { Agent, Goal, TaskStatus, AgentStatus } from './types';
import { INITIAL_AGENTS, INITIAL_GOALS } from './constants';
import Dashboard from './components/Dashboard';
import Workforce from './components/Workforce';
import TaskManager from './components/TaskManager';
import KnowledgeBase from './components/KnowledgeBase';
import MemorySystem from './components/MemorySystem';
import { translations, Language } from './translations';

type Theme = 'light' | 'dark' | 'system';

const App: React.FC = () => {
  const [lang, setLang] = useState<Language>('zh');
  const [theme, setTheme] = useState<Theme>(() => {
    return (localStorage.getItem('theme') as Theme) || 'system';
  });
  const [activeTab, setActiveTab] = useState('dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [agents, setAgents] = useState<Agent[]>(INITIAL_AGENTS);
  const [goals, setGoals] = useState<Goal[]>(INITIAL_GOALS);
  const [notifications, setNotifications] = useState<string[]>([]);

  const t = translations[lang];

  useEffect(() => {
    const root = window.document.documentElement;
    const applyTheme = (t: 'light' | 'dark') => {
      if (t === 'dark') root.classList.add('dark');
      else root.classList.remove('dark');
    };

    if (theme === 'system') {
      const systemTheme = window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
      applyTheme(systemTheme);
      const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
      const handleChange = (e: MediaQueryListEvent) => applyTheme(e.matches ? 'dark' : 'light');
      mediaQuery.addEventListener('change', handleChange);
      return () => mediaQuery.removeEventListener('change', handleChange);
    } else {
      applyTheme(theme);
    }
    localStorage.setItem('theme', theme);
  }, [theme]);

  const addNotification = (msg: string) => setNotifications(prev => [msg, ...prev].slice(0, 5));

  const tabs = [
    { id: 'dashboard', label: t.nav.dashboard, icon: LayoutDashboard },
    { id: 'workforce', label: t.nav.workforce, icon: Users },
    { id: 'tasks', label: t.nav.tasks, icon: Target },
    { id: 'knowledge', label: t.nav.knowledge, icon: Database },
    { id: 'memory', label: t.nav.memory, icon: BrainCircuit },
  ];

  const renderContent = () => {
    const props = { agents, goals };
    switch (activeTab) {
      case 'dashboard': return <Dashboard {...props} t={t.dashboard} />;
      case 'workforce': return <Workforce agents={agents} setAgents={setAgents} t={t.workforce} />;
      case 'tasks': return <TaskManager goals={goals} setGoals={setGoals} agents={agents} onLog={addNotification} t={t.tasks} lang={lang} />;
      case 'knowledge': return <KnowledgeBase t={t.knowledge} />;
      case 'memory': return <MemorySystem t={t.memory} />;
      default: return <Dashboard {...props} t={t.dashboard} />;
    }
  };

  return (
    <div className="flex h-screen overflow-hidden selection:bg-emerald-500/30">
      {/* Sidebar */}
      <aside className={`glass-panel z-50 transition-all duration-500 flex flex-col ${sidebarOpen ? 'w-64' : 'w-20'} h-full border-r`}>
        <div className="p-6 flex items-center gap-3">
          <div className="w-9 h-9 bg-emerald-500 rounded-xl flex items-center justify-center shadow-lg shadow-emerald-500/20">
            <Cpu className="text-white w-5 h-5" />
          </div>
          {sidebarOpen && <span className="font-bold text-xl tracking-tight uppercase bg-clip-text text-transparent bg-gradient-to-br from-emerald-500 to-emerald-700">{t.brand}</span>}
        </div>

        <nav className="flex-1 px-4 space-y-1.5 mt-2">
          {tabs.map((tab) => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-300 ${
                activeTab === tab.id 
                ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-500 shadow-sm border border-emerald-500/10' 
                : 'text-zinc-500 dark:text-zinc-400 hover:bg-zinc-500/5 hover:text-zinc-900 dark:hover:text-white'
              }`}
            >
              <tab.icon className={`w-5 h-5 transition-transform duration-300 ${activeTab === tab.id ? 'scale-110' : ''}`} />
              {sidebarOpen && <span className="font-medium text-sm">{tab.label}</span>}
            </button>
          ))}
        </nav>

        <div className="p-4 border-t border-zinc-500/10">
          <div className={`flex items-center gap-3 p-3 rounded-2xl bg-zinc-500/5 ${sidebarOpen ? '' : 'justify-center'}`}>
            <div className="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center text-[10px] font-bold">JD</div>
            {sidebarOpen && (
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold truncate">Jane Doe</p>
                <p className="text-[10px] text-zinc-500 truncate">{t.nav.settings}</p>
              </div>
            )}
            {sidebarOpen && <Settings className="w-4 h-4 text-zinc-400 cursor-pointer hover:text-zinc-900 dark:hover:text-white transition-colors" />}
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col relative overflow-hidden bg-white dark:bg-black transition-colors duration-500">
        <div className="absolute inset-0 scan-line"></div>
        
        {/* Header */}
        <header className="h-16 border-b border-zinc-500/5 glass-panel flex items-center justify-between px-6 z-10">
          <div className="flex items-center gap-4">
            <button onClick={() => setSidebarOpen(!sidebarOpen)} className="p-2 hover:bg-zinc-500/5 rounded-full transition-colors">
              <Menu className="w-5 h-5 text-zinc-500" />
            </button>
            <div className="hidden md:flex items-center gap-2 text-[11px] font-medium text-zinc-400 uppercase tracking-widest">
              <ShieldCheck className="w-3.5 h-3.5 text-emerald-500" />
              <span>{t.header.status}: <span className="text-emerald-600 dark:text-emerald-500">{t.header.optimal}</span></span>
            </div>
          </div>

          <div className="flex items-center gap-4">
            {/* Theme & Lang Controls */}
            <div className="flex items-center gap-2">
              <div className="flex items-center bg-zinc-500/5 rounded-full p-1 border border-zinc-500/5">
                {[
                  { id: 'light', icon: Sun },
                  { id: 'system', icon: Monitor },
                  { id: 'dark', icon: Moon }
                ].map((item) => (
                  <button 
                    key={item.id}
                    onClick={() => setTheme(item.id as Theme)}
                    className={`p-1.5 rounded-full transition-all duration-300 ${theme === item.id ? 'bg-white dark:bg-zinc-700 shadow-sm text-emerald-600 dark:text-emerald-400' : 'text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-300'}`}
                  >
                    <item.icon className="w-3.5 h-3.5" />
                  </button>
                ))}
              </div>

              <div className="flex items-center bg-zinc-500/5 rounded-full p-1 border border-zinc-500/5">
                {['zh', 'en'].map((l) => (
                  <button 
                    key={l}
                    onClick={() => setLang(l as Language)}
                    className={`px-3 py-1 rounded-full text-[10px] font-bold transition-all duration-300 ${lang === l ? 'bg-white dark:bg-zinc-700 shadow-sm text-emerald-600 dark:text-emerald-400' : 'text-zinc-400'}`}
                  >
                    {l.toUpperCase()}
                  </button>
                ))}
              </div>
            </div>

            <button className="relative p-2.5 hover:bg-zinc-500/5 rounded-full transition-colors text-zinc-400">
              <Bell className="w-5 h-5" />
              {notifications.length > 0 && (
                <span className="absolute top-2.5 right-2.5 w-1.5 h-1.5 bg-red-500 rounded-full border-2 border-white dark:border-black"></span>
              )}
            </button>
          </div>
        </header>

        {/* Content Area */}
        <div className="flex-1 overflow-y-auto p-6 lg:p-10 z-10 custom-scrollbar scroll-smooth">
          <div className="max-w-7xl mx-auto">
            {renderContent()}
          </div>
        </div>
      </main>
    </div>
  );
};

export default App;
