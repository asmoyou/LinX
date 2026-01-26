import React from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { 
  LayoutDashboard, 
  Users, 
  Target, 
  Database, 
  BrainCircuit,
  Code2,
  Settings,
  ChevronLeft,
  ChevronRight
} from 'lucide-react';

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggle }) => {
  const { t } = useTranslation();

  const navItems = [
    { path: '/', icon: LayoutDashboard, label: t('nav.dashboard') },
    { path: '/workforce', icon: Users, label: t('nav.workforce') },
    { path: '/tasks', icon: Target, label: t('nav.tasks') },
    { path: '/knowledge', icon: Database, label: t('nav.knowledge') },
    { path: '/memory', icon: BrainCircuit, label: t('nav.memory') },
    { path: '/skills', icon: Code2, label: t('nav.skills') },
    { path: '/settings', icon: Settings, label: t('nav.settings') },
  ];

  return (
    <aside
      className={`glass-panel z-30 transition-all duration-500 flex flex-col ${
        isCollapsed ? 'w-20' : 'w-64'
      } h-full border-r border-zinc-500/5 relative`}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className="p-6 flex items-center gap-3">
        <img 
          src="/logo-sm.webp" 
          alt="LinX Logo" 
          className="w-9 h-9 object-contain"
        />
        {!isCollapsed && (
          <span className="font-bold text-xl tracking-tight uppercase bg-clip-text text-transparent bg-gradient-to-br from-emerald-500 to-emerald-700">
            {t('app.brandName')}
          </span>
        )}
      </div>

      {/* Collapse Toggle Button */}
      <button
        onClick={onToggle}
        className="absolute -right-3.5 top-24 w-7 h-7 rounded-lg bg-gradient-to-br from-emerald-500 to-emerald-600 shadow-lg shadow-emerald-500/25 flex items-center justify-center text-white hover:shadow-xl hover:shadow-emerald-500/40 transition-all duration-300 hover:scale-105 z-10 group"
        aria-label={isCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
        title={isCollapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')}
      >
        {isCollapsed ? (
          <ChevronRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
        ) : (
          <ChevronLeft className="w-4 h-4 group-hover:-translate-x-0.5 transition-transform" />
        )}
      </button>

      {/* Navigation */}
      <nav className="flex-1 px-4 space-y-1.5 mt-2" aria-label="Primary navigation">
        {navItems.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              `w-full flex items-center gap-3 px-3 py-2.5 rounded-xl transition-all duration-300 ${
                isActive
                  ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-500 shadow-sm border border-emerald-500/10'
                  : 'text-zinc-600 dark:text-zinc-400 hover:bg-emerald-50 hover:text-emerald-700 dark:hover:bg-emerald-500/5 dark:hover:text-emerald-400'
              }`
            }
            title={isCollapsed ? item.label : undefined}
            aria-label={item.label}
          >
            {({ isActive }) => (
              <>
                <item.icon 
                  className={`w-5 h-5 transition-transform duration-300 ${
                    isActive ? 'scale-110' : ''
                  }`} 
                  aria-hidden="true" 
                />
                {!isCollapsed && <span className="font-medium text-sm">{item.label}</span>}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* User Profile */}
      <div className="p-4 border-t border-zinc-500/10">
        <NavLink
          to="/profile"
          className={({ isActive }) =>
            `flex items-center gap-3 p-3 rounded-2xl transition-all duration-300 ${
              isActive
                ? 'bg-emerald-500/10 border border-emerald-500/10'
                : 'bg-zinc-100 dark:bg-zinc-500/5 hover:bg-emerald-50 dark:hover:bg-emerald-500/5'
            } ${isCollapsed ? 'justify-center' : ''}`
          }
        >
          <div className="w-8 h-8 rounded-full bg-zinc-200 dark:bg-zinc-800 flex items-center justify-center text-[10px] font-bold text-zinc-700 dark:text-zinc-300">
            AD
          </div>
          {!isCollapsed && (
            <>
              <div className="flex-1 min-w-0">
                <p className="text-xs font-semibold truncate text-zinc-800 dark:text-zinc-200">Admin User</p>
                <p className="text-[10px] text-zinc-500 truncate">{t('nav.settings')}</p>
              </div>
              <Settings className="w-4 h-4 text-zinc-400" />
            </>
          )}
        </NavLink>
      </div>
    </aside>
  );
};
