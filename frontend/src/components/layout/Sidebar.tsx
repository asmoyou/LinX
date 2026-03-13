import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  LayoutDashboard,
  Users,
  Rocket,
  Database,
  Brain,
  Code2,
  Cpu,
  Building2,
  Settings,
  Mail,
  Shield,
  User,
  UserCog,
  ShieldCheck,
  ChevronDown,
  GripVertical,
} from 'lucide-react';
import { useAuthStore, useUserStore } from '@/stores';

interface SidebarProps {
  isCollapsed: boolean;
  onToggle: () => void;
}

const COMPACT_HEIGHT_BREAKPOINT = 760;
const MAX_QUICK_ACCESS_ITEMS = 5;
const MIN_DYNAMIC_QUICK_ACCESS_USAGE = 2;
const QUICK_ACCESS_STORAGE_KEY_PREFIX = 'linx-sidebar-nav-usage';
const QUICK_ACCESS_ORDER_STORAGE_KEY_PREFIX = 'linx-sidebar-quick-order';
const DEFAULT_QUICK_ACCESS_PATHS = ['/workforce', '/tasks', '/dashboard'] as const;

type NavItem = {
  path: string;
  icon: React.ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
  label: string;
  requiredRoles?: string[];
};

type NavSection = {
  id: string;
  label: string;
  items: NavItem[];
};

const isPathMatch = (currentPath: string, targetPath: string): boolean => {
  if (targetPath === '/dashboard') {
    return currentPath === '/' || currentPath === '/dashboard';
  }
  return currentPath === targetPath || currentPath.startsWith(`${targetPath}/`);
};

const safeParseUsage = (value: string | null): Record<string, number> => {
  if (!value) return {};

  try {
    const parsed = JSON.parse(value) as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(parsed).filter(
        ([key, count]) =>
          typeof key === 'string' && typeof count === 'number' && Number.isFinite(count) && count > 0
      )
    );
  } catch {
    return {};
  }
};

const safeParseOrder = (value: string | null): string[] => {
  if (!value) return [];

  try {
    const parsed = JSON.parse(value) as unknown;
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === 'string' && item.length > 0);
  } catch {
    return [];
  }
};

const reorderPathsWithPosition = (
  paths: string[],
  sourcePath: string,
  targetPath: string,
  position: 'before' | 'after'
): string[] => {
  if (sourcePath === targetPath) return paths;

  const sourceIndex = paths.indexOf(sourcePath);
  const targetIndex = paths.indexOf(targetPath);
  if (sourceIndex < 0 || targetIndex < 0) return paths;

  const reordered = [...paths];
  reordered.splice(sourceIndex, 1);
  const adjustedTargetIndex = reordered.indexOf(targetPath);
  if (adjustedTargetIndex < 0) return paths;

  const insertIndex = position === 'before' ? adjustedTargetIndex : adjustedTargetIndex + 1;
  reordered.splice(insertIndex, 0, sourcePath);
  return reordered;
};

export const Sidebar: React.FC<SidebarProps> = ({ isCollapsed }) => {
  const { t } = useTranslation();
  const location = useLocation();
  const { user } = useAuthStore();
  const { profile } = useUserStore();
  const [showUserCard, setShowUserCard] = useState(false);
  const [isCompactHeight, setIsCompactHeight] = useState(
    typeof window !== 'undefined' && window.innerHeight < COMPACT_HEIGHT_BREAKPOINT
  );
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    assets: true,
    organization: true,
    governance: true,
    extension: false,
  });

  // Use profile if available, fallback to auth user
  const displayUser = profile || user;
  const userId = displayUser?.id || user?.id || 'guest';
  const avatarUrl = profile?.attributes?.avatar_url;
  const displayName = profile?.displayName || profile?.attributes?.display_name;
  const username = displayUser?.username || 'User';
  const email = displayUser?.email || '';
  const role = displayUser?.role || 'user';
  const initials = (displayName || username).substring(0, 2).toUpperCase();
  const usageStorageKey = `${QUICK_ACCESS_STORAGE_KEY_PREFIX}:${userId}`;
  const quickAccessOrderStorageKey = `${QUICK_ACCESS_ORDER_STORAGE_KEY_PREFIX}:${userId}`;
  const [navUsage, setNavUsage] = useState<Record<string, number>>({});
  const [quickAccessOrder, setQuickAccessOrder] = useState<string[]>([]);
  const [draggingQuickPath, setDraggingQuickPath] = useState<string | null>(null);
  const [dragOverQuickPath, setDragOverQuickPath] = useState<string | null>(null);
  const [dragOverQuickPosition, setDragOverQuickPosition] = useState<'before' | 'after' | null>(
    null
  );

  useEffect(() => {
    const updateCompactMode = () => {
      setIsCompactHeight(window.innerHeight < COMPACT_HEIGHT_BREAKPOINT);
    };

    updateCompactMode();
    window.addEventListener('resize', updateCompactMode);
    return () => window.removeEventListener('resize', updateCompactMode);
  }, []);

  const navSections = useMemo<NavSection[]>(
    () => [
      {
        id: 'operations',
        label: t('nav.groups.operations', 'Operations'),
        items: [
          { path: '/dashboard', icon: LayoutDashboard, label: t('nav.dashboard') },
          { path: '/workforce', icon: Users, label: t('nav.workforce') },
          { path: '/tasks', icon: Rocket, label: t('nav.tasks') },
        ],
      },
      {
        id: 'assets',
        label: t('nav.groups.assets', 'Assets'),
        items: [
          { path: '/knowledge', icon: Database, label: t('nav.knowledge') },
          { path: '/memory/user-memory', icon: User, label: t('nav.userMemory') },
          {
            path: '/memory/skill-proposals',
            icon: Brain,
            label: t('nav.skillProposals'),
          },
          { path: '/skills', icon: Code2, label: t('nav.skills') },
        ],
      },
      {
        id: 'organization',
        label: t('nav.groups.organization', 'Organization'),
        items: [{ path: '/departments', icon: Building2, label: t('nav.departments') }],
      },
      {
        id: 'governance',
        label: t('nav.groups.governance', 'Governance'),
        items: [
          { path: '/settings', icon: Settings, label: t('nav.settings') },
          {
            path: '/user-management',
            icon: UserCog,
            label: t('nav.userManagement'),
            requiredRoles: ['admin', 'manager'],
          },
          {
            path: '/role-management',
            icon: ShieldCheck,
            label: t('nav.roleManagement'),
            requiredRoles: ['admin', 'manager'],
          },
        ],
      },
      {
        id: 'extension',
        label: t('nav.groups.extension', 'Extensions'),
        items: [{ path: '/robots', icon: Cpu, label: t('nav.robots') }],
      },
    ],
    [t]
  );

  const hasAccess = useCallback(
    (item: NavItem): boolean => !item.requiredRoles || item.requiredRoles.includes(role),
    [role]
  );

  const filteredNavSections = useMemo(
    () =>
      navSections
        .map((section) => ({
          ...section,
          items: section.items.filter(hasAccess),
        }))
        .filter((section) => section.items.length > 0),
    [hasAccess, navSections]
  );

  const allVisibleNavItems = useMemo(
    () => filteredNavSections.flatMap((section) => section.items),
    [filteredNavSections]
  );

  const navOrder = useMemo(
    () =>
      allVisibleNavItems.reduce<Record<string, number>>((acc, item, index) => {
        acc[item.path] = index;
        return acc;
      }, {}),
    [allVisibleNavItems]
  );

  useEffect(() => {
    if (typeof window === 'undefined') return;
    // Load persisted usage when the active user changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNavUsage(safeParseUsage(window.localStorage.getItem(usageStorageKey)));
  }, [usageStorageKey]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    // Restore the saved quick access ordering for the active user.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setQuickAccessOrder(safeParseOrder(window.localStorage.getItem(quickAccessOrderStorageKey)));
  }, [quickAccessOrderStorageKey]);

  useEffect(() => {
    if (typeof window === 'undefined') return;
    window.localStorage.setItem(quickAccessOrderStorageKey, JSON.stringify(quickAccessOrder));
  }, [quickAccessOrder, quickAccessOrderStorageKey]);

  const currentNavPath = useMemo(() => {
    const sortedPaths = allVisibleNavItems
      .map((item) => item.path)
      .sort((left, right) => right.length - left.length);

    return sortedPaths.find((path) => isPathMatch(location.pathname, path));
  }, [allVisibleNavItems, location.pathname]);

  useEffect(() => {
    if (!currentNavPath || typeof window === 'undefined') return;

    // Navigation usage is persisted as the active route changes.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setNavUsage((prev) => {
      const next = {
        ...prev,
        [currentNavPath]: (prev[currentNavPath] || 0) + 1,
      };
      window.localStorage.setItem(usageStorageKey, JSON.stringify(next));
      return next;
    });
  }, [currentNavPath, location.pathname, usageStorageKey]);

  const defaultQuickAccessItems = useMemo(
    () =>
      DEFAULT_QUICK_ACCESS_PATHS.map((path) =>
        allVisibleNavItems.find((item) => item.path === path)
      ).filter((item): item is NavItem => Boolean(item)),
    [allVisibleNavItems]
  );

  const dynamicQuickAccessItems = useMemo(() => {
    const defaultPathSet = new Set(defaultQuickAccessItems.map((item) => item.path));

    return allVisibleNavItems
      .filter((item) => !defaultPathSet.has(item.path))
      .filter((item) => (navUsage[item.path] || 0) >= MIN_DYNAMIC_QUICK_ACCESS_USAGE)
      .sort((left, right) => {
        const usageDelta = (navUsage[right.path] || 0) - (navUsage[left.path] || 0);
        if (usageDelta !== 0) return usageDelta;
        return (navOrder[left.path] || 0) - (navOrder[right.path] || 0);
      });
  }, [allVisibleNavItems, defaultQuickAccessItems, navOrder, navUsage]);

  const quickAccessCandidates = useMemo(() => {
    const next: NavItem[] = [...defaultQuickAccessItems];
    for (const item of dynamicQuickAccessItems) {
      if (!next.some((existing) => existing.path === item.path)) {
        next.push(item);
      }
    }
    return next;
  }, [defaultQuickAccessItems, dynamicQuickAccessItems]);

  const quickAccessItems = useMemo(() => {
    const pathToItem = new Map(quickAccessCandidates.map((item) => [item.path, item]));
    const ordered: NavItem[] = [];
    const seen = new Set<string>();

    quickAccessOrder.forEach((path) => {
      const matched = pathToItem.get(path);
      if (!matched || seen.has(path)) return;
      ordered.push(matched);
      seen.add(path);
    });

    quickAccessCandidates.forEach((item) => {
      if (seen.has(item.path)) return;
      ordered.push(item);
      seen.add(item.path);
    });

    return ordered.slice(0, MAX_QUICK_ACCESS_ITEMS);
  }, [quickAccessCandidates, quickAccessOrder]);

  const quickAccessPathSet = useMemo(
    () => new Set(quickAccessItems.map((item) => item.path)),
    [quickAccessItems]
  );

  useEffect(() => {
    const quickPaths = new Set(quickAccessCandidates.map((item) => item.path));
    // Keep persisted custom order limited to the currently visible quick links.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setQuickAccessOrder((prev) => prev.filter((path) => quickPaths.has(path)));
  }, [quickAccessCandidates]);

  const isItemActive = (item: NavItem): boolean => isPathMatch(location.pathname, item.path);

  useEffect(() => {
    // Auto-expand the section containing the active item when needed.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setExpandedSections((prev) => {
      let changed = false;
      const next = { ...prev };

      filteredNavSections.forEach((section) => {
        if (
          section.items.some(
            (item) => isItemActive(item) && !quickAccessPathSet.has(item.path)
          ) &&
          !next[section.id]
        ) {
          next[section.id] = true;
          changed = true;
        }
      });

      return changed ? next : prev;
    });
  }, [filteredNavSections, location.pathname, quickAccessPathSet]);

  const toggleSection = (sectionId: string) => {
    setExpandedSections((prev) => ({
      ...prev,
      [sectionId]: !prev[sectionId],
    }));
  };

  const handleQuickItemDragStart = (event: React.DragEvent<HTMLDivElement>, path: string) => {
    if (isCollapsed) return;
    setDraggingQuickPath(path);
    setDragOverQuickPath(null);
    setDragOverQuickPosition(null);
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', path);
  };

  const handleQuickItemDrop = (
    event: React.DragEvent<HTMLDivElement>,
    targetPath: string
  ) => {
    event.preventDefault();

    if (!draggingQuickPath || draggingQuickPath === targetPath) {
      setDraggingQuickPath(null);
      setDragOverQuickPath(null);
      setDragOverQuickPosition(null);
      return;
    }

    const rect = event.currentTarget.getBoundingClientRect();
    const position: 'before' | 'after' =
      event.clientY < rect.top + rect.height / 2 ? 'before' : 'after';

    const currentPaths = quickAccessItems.map((item) => item.path);
    const reordered = reorderPathsWithPosition(
      currentPaths,
      draggingQuickPath,
      targetPath,
      position
    );
    setQuickAccessOrder(reordered);
    setDraggingQuickPath(null);
    setDragOverQuickPath(null);
    setDragOverQuickPosition(null);
  };

  return (
    <aside
      className={`glass-panel z-30 transition-all duration-500 flex flex-col ${
        isCollapsed ? 'w-20' : 'w-64'
      } h-full min-h-0 border-r border-zinc-500/5 relative overflow-hidden`}
      role="navigation"
      aria-label="Main navigation"
    >
      {/* Logo */}
      <div className={`flex items-center gap-3 ${isCompactHeight ? 'p-4' : 'p-6'}`}>
        <img 
          src="/logo-sm.webp" 
          alt="LinX Logo" 
          className={`${isCompactHeight ? 'w-8 h-8' : 'w-9 h-9'} object-contain`}
        />
        {!isCollapsed && (
          <span
            className={`font-bold tracking-tight uppercase bg-clip-text text-transparent bg-gradient-to-br from-emerald-500 to-emerald-700 ${
              isCompactHeight ? 'text-lg' : 'text-xl'
            }`}
          >
            {t('app.brandName')}
          </span>
        )}
      </div>

      {/* Navigation */}
      <div className="flex-1 min-h-0 px-4 mt-2">
        <nav
          className={`h-full overflow-y-auto custom-scrollbar pr-1 ${
            isCompactHeight ? 'space-y-3' : 'space-y-4'
          }`}
          aria-label="Primary navigation"
        >
          {!isCollapsed && (
            <p className="px-2 text-[10px] font-semibold tracking-[0.14em] uppercase text-zinc-500 dark:text-zinc-400">
              {t('nav.quickAccess', 'Quick Access')}
            </p>
          )}

          <div className={`${isCompactHeight ? 'space-y-1' : 'space-y-1.5'}`}>
            {quickAccessItems.map((item) => {
              const isDragSource = draggingQuickPath === item.path;
              const isDropTarget =
                dragOverQuickPath === item.path && draggingQuickPath !== item.path;
              const showDropBefore = isDropTarget && dragOverQuickPosition === 'before';
              const showDropAfter = isDropTarget && dragOverQuickPosition === 'after';

              return (
                <div
                  key={item.path}
                  draggable={!isCollapsed}
                  onDragStart={(event) => handleQuickItemDragStart(event, item.path)}
                  onDragOver={(event) => {
                    event.preventDefault();
                    event.dataTransfer.dropEffect = 'move';
                    if (isCollapsed || !draggingQuickPath) return;
                    if (draggingQuickPath === item.path) return;

                    const rect = event.currentTarget.getBoundingClientRect();
                    const nextPosition: 'before' | 'after' =
                      event.clientY < rect.top + rect.height / 2 ? 'before' : 'after';

                    if (
                      dragOverQuickPath !== item.path ||
                      dragOverQuickPosition !== nextPosition
                    ) {
                      setDragOverQuickPath(item.path);
                      setDragOverQuickPosition(nextPosition);
                    }
                  }}
                  onDrop={(event) => handleQuickItemDrop(event, item.path)}
                  onDragEnd={() => {
                    setDraggingQuickPath(null);
                    setDragOverQuickPath(null);
                    setDragOverQuickPosition(null);
                  }}
                  className={`${
                    isDragSource ? 'opacity-70 scale-[0.98]' : 'opacity-100'
                  } relative transition-all`}
                >
                  {showDropBefore && (
                    <div className="absolute -top-1 left-2 right-2 h-0.5 rounded-full bg-emerald-400 dark:bg-emerald-500" />
                  )}
                  {showDropAfter && (
                    <div className="absolute -bottom-1 left-2 right-2 h-0.5 rounded-full bg-emerald-400 dark:bg-emerald-500" />
                  )}
                  <NavLink
                    to={item.path}
                    end={item.path === '/dashboard'}
                    className={({ isActive }) =>
                      `w-full flex items-center gap-3 rounded-xl transition-all duration-300 ${
                        isCompactHeight ? 'px-3 py-2' : 'px-3 py-2.5'
                      } ${
                        isActive
                          ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-500 shadow-sm border border-emerald-500/10'
                          : 'text-zinc-600 dark:text-zinc-400 hover:bg-emerald-50 hover:text-emerald-700 dark:hover:bg-emerald-500/5 dark:hover:text-emerald-400'
                      } ${!isCollapsed ? 'cursor-grab active:cursor-grabbing' : ''}`
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
                        {!isCollapsed && (
                          <span
                            className={`font-medium flex-1 ${
                              isCompactHeight ? 'text-[13px]' : 'text-sm'
                            }`}
                          >
                            {item.label}
                          </span>
                        )}
                        {!isCollapsed && (
                          <GripVertical
                            className="w-3.5 h-3.5 text-zinc-400/90"
                            aria-hidden="true"
                          />
                        )}
                      </>
                    )}
                  </NavLink>
                </div>
              );
            })}
          </div>

          {filteredNavSections.map((section) => (
            <div key={section.id} className="pt-1">
              {!isCollapsed && (
                <button
                  type="button"
                  onClick={() => toggleSection(section.id)}
                  className="w-full px-2 py-1.5 flex items-center justify-between text-[10px] font-semibold tracking-[0.14em] uppercase text-zinc-500 dark:text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-300"
                >
                  <span>{section.label}</span>
                  <ChevronDown
                    className={`w-3.5 h-3.5 transition-transform ${
                      expandedSections[section.id] ? '' : '-rotate-90'
                    }`}
                  />
                </button>
              )}

              {(isCollapsed || expandedSections[section.id]) && (
                <div className={`${isCompactHeight ? 'space-y-1' : 'space-y-1.5'}`}>
                  {section.items.map((item) => (
                    <NavLink
                      key={item.path}
                      to={item.path}
                      end={item.path === '/dashboard'}
                      className={({ isActive }) => {
                        const showActive = isActive && !quickAccessPathSet.has(item.path);
                        return `w-full flex items-center gap-3 rounded-xl transition-all duration-300 ${
                          isCompactHeight ? 'px-3 py-2' : 'px-3 py-2.5'
                        } ${
                          showActive
                            ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-500 shadow-sm border border-emerald-500/10'
                            : 'text-zinc-600 dark:text-zinc-400 hover:bg-emerald-50 hover:text-emerald-700 dark:hover:bg-emerald-500/5 dark:hover:text-emerald-400'
                        }`;
                      }}
                      title={isCollapsed ? item.label : undefined}
                      aria-label={item.label}
                    >
                      {({ isActive }) => {
                        const showActive = isActive && !quickAccessPathSet.has(item.path);
                        return (
                          <>
                            <item.icon
                              className={`w-5 h-5 transition-transform duration-300 ${
                                showActive ? 'scale-110' : ''
                              }`}
                              aria-hidden="true"
                            />
                            {!isCollapsed && (
                              <span className={`font-medium ${isCompactHeight ? 'text-[13px]' : 'text-sm'}`}>
                                {item.label}
                              </span>
                            )}
                          </>
                        );
                      }}
                    </NavLink>
                  ))}
                </div>
              )}
            </div>
          ))}
        </nav>
      </div>

      {/* User Profile */}
      <div
        className={`border-t border-zinc-500/10 relative ${
          isCompactHeight ? 'p-3' : 'p-4'
        } flex-shrink-0`}
      >
        <div
          className="relative"
          onMouseEnter={() => !isCollapsed && setShowUserCard(true)}
          onMouseLeave={() => setShowUserCard(false)}
        >
          <NavLink
            to="/profile"
            className={({ isActive }) =>
              `flex items-center gap-3 ${
                isCompactHeight ? 'p-2.5' : 'p-3'
              } rounded-2xl transition-all duration-300 ${
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
