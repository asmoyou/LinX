import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard,
  Users,
  Rocket,
  Database,
  BrainCircuit,
  Code2,
  Building2,
  Settings,
  Mail,
  Shield,
  UserCog,
  ShieldCheck
} from 'lucide-react';
import { useAuthStore, useUserStore } from '@/stores';

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed, onToggle }) => {
  const { t } = useTranslation();
  const { user } = useAuthStore();
  const { profile } = useUserStore();
  const [showUserCard, setShowUserCard] = useState(false);

  // Use profile if available, fallback to auth user
  const displayUser = profile || user;
  const avatarUrl = profile?.attributes?.avatar_url;
  const displayName = profile?.displayName || profile?.attributes?.display_name;
  const username = displayUser?.username || 'User';
  const email = displayUser?.email || '';
  const role = displayUser?.role || 'user';
  const initials = (displayName || username).substring(0, 2).toUpperCase();

  const navItems = [
    { path: '/', icon: LayoutDashboard, label: t('nav.dashboard') },
    { path: '/workforce', icon: Users, label: t('nav.workforce') },
    { path: '/tasks', icon: Rocket, label: t('nav.tasks') },
    { path: '/knowledge', icon: Database, label: t('nav.knowledge') },
    { path: '/memory', icon: BrainCircuit, label: t('nav.memory') },
    { path: '/skills', icon: Code2, label: t('nav.skills') },
    { path: '/departments', icon: Building2, label: t('nav.departments') },
    { path: '/user-management', icon: UserCog, label: t('nav.userManagement'), requiredRoles: ['admin', 'manager'] as string[] },
    { path: '/role-management', icon: ShieldCheck, label: t('nav.roleManagement'), requiredRoles: ['admin', 'manager'] as string[] },
    { path: '/settings', icon: Settings, label: t('nav.settings') },
  ];

  const filteredNavItems = navItems.filter((item) => {
    if (!item.requiredRoles) return true;
    return item.requiredRoles.includes(role);
  });

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

      {/* Navigation */}
      <nav className="flex-1 px-4 space-y-1.5 mt-2" aria-label="Primary navigation">
        {filteredNavItems.map((item) => (
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
      <div className="p-4 border-t border-zinc-500/10 relative">
        <div
          className="relative"
          onMouseEnter={() => !isCollapsed && setShowUserCard(true)}
          onMouseLeave={() => setShowUserCard(false)}
        >
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
            <div className="w-8 h-8 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-[10px] font-bold text-white overflow-hidden flex-shrink-0">
              {avatarUrl ? (
                <img src={avatarUrl} alt={displayName || username} className="w-full h-full object-cover" />
              ) : (
                initials
              )}
            </div>
            {!isCollapsed && (
              <>
                <div className="flex-1 min-w-0">
                  <p className="text-xs font-semibold truncate text-zinc-800 dark:text-zinc-200">
                    {displayName || username}
                  </p>
                  <p className="text-[10px] text-zinc-500 truncate">
                    {role}
                  </p>
                </div>
                <Settings className="w-4 h-4 text-zinc-400" />
              </>
            )}
          </NavLink>

          {/* User Info Card - Shows on hover */}
          {showUserCard && !isCollapsed && (
            <div className="absolute bottom-full left-0 mb-2 w-64 bg-white dark:bg-zinc-800 rounded-xl shadow-2xl border border-zinc-200 dark:border-zinc-700 p-4 z-50 animate-in fade-in slide-in-from-bottom-2 duration-200">
              {/* Avatar and Name */}
              <div className="flex items-center gap-3 mb-3 pb-3 border-b border-zinc-200 dark:border-zinc-700">
                <div className="w-12 h-12 rounded-full bg-gradient-to-br from-emerald-500 to-cyan-500 flex items-center justify-center text-sm font-bold text-white overflow-hidden flex-shrink-0">
                  {avatarUrl ? (
                    <img src={avatarUrl} alt={displayName || username} className="w-full h-full object-cover" />
                  ) : (
                    initials
                  )}
                </div>
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold text-zinc-900 dark:text-white truncate">
                    {displayName || username}
                  </p>
                  {displayName && (
                    <p className="text-xs text-zinc-500 dark:text-zinc-400 truncate">
                      @{username}
                    </p>
                  )}
                </div>
              </div>

              {/* User Details */}
              <div className="space-y-2">
                {/* Email */}
                {email && (
                  <div className="flex items-start gap-2">
                    <Mail className="w-3.5 h-3.5 text-zinc-400 mt-0.5 flex-shrink-0" />
                    <div className="flex-1 min-w-0">
                      <p className="text-[10px] text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Email</p>
                      <p className="text-xs text-zinc-700 dark:text-zinc-300 truncate">{email}</p>
                    </div>
                  </div>
                )}

                {/* Role */}
                <div className="flex items-start gap-2">
                  <Shield className="w-3.5 h-3.5 text-zinc-400 mt-0.5 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-[10px] text-zinc-500 dark:text-zinc-400 uppercase tracking-wide">Role</p>
                    <p className="text-xs text-zinc-700 dark:text-zinc-300 capitalize">{role}</p>
                  </div>
                </div>
              </div>

              {/* Action Hint */}
              <div className="mt-3 pt-3 border-t border-zinc-200 dark:border-zinc-700">
                <p className="text-[10px] text-zinc-400 dark:text-zinc-500 text-center">
                  Click to view profile settings
                </p>
              </div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
};
