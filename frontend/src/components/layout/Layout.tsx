import React, { useEffect } from 'react';
import { Outlet, useLocation } from 'react-router-dom';

import { notificationsApi } from '@/api/notifications';
import { useProjectExecutionStore } from '@/stores/projectExecutionStore';
import { useNotificationStore } from '@/stores/notificationStore';
import { useThemeStore } from '@/stores/themeStore';

import { Header } from './Header';
import { Sidebar } from './Sidebar';

export const Layout: React.FC = () => {
  const location = useLocation();
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const { applyTheme } = useThemeStore();
  const replaceServerNotifications = useNotificationStore((state) => state.replaceServerNotifications);
  const loadProjects = useProjectExecutionStore((state) => state.loadProjects);
  const loadRuns = useProjectExecutionStore((state) => state.loadRuns);

  const syncNotifications = React.useCallback(async () => {
    try {
      const response = await notificationsApi.getAll({
        status: 'all',
        limit: 100,
        offset: 0,
      });
      replaceServerNotifications(response.items);
    } catch {
      // API interceptor handles user-visible error toast when needed.
    }
  }, [replaceServerNotifications]);

  useEffect(() => {
    applyTheme();

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      applyTheme();
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [applyTheme]);

  useEffect(() => {
    const handleKeyPress = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key === 'b') {
        event.preventDefault();
        setSidebarCollapsed((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  useEffect(() => {
    document.documentElement.style.setProperty('--sidebar-width', sidebarCollapsed ? '5rem' : '16rem');
    document.documentElement.style.setProperty('--app-header-height', '4rem');

    return () => {
      document.documentElement.style.removeProperty('--sidebar-width');
      document.documentElement.style.removeProperty('--app-header-height');
    };
  }, [sidebarCollapsed]);

  useEffect(() => {
    const handleResize = () => {
      if (window.innerWidth < 768) {
        setSidebarCollapsed(true);
      }
    };

    handleResize();
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  useEffect(() => {
    let cancelled = false;

    const loadCurrentRouteResources = async () => {
      if (cancelled) return;
      const jobs: Array<Promise<unknown>> = [syncNotifications()];

      if (location.pathname.startsWith('/projects')) {
        jobs.push(loadProjects());
      }
      if (location.pathname.startsWith('/runs')) {
        jobs.push(loadRuns());
      }
      await Promise.allSettled(jobs);
    };

    void loadCurrentRouteResources();

    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void loadCurrentRouteResources();
    }, 60_000);

    return () => {
      cancelled = true;
      window.clearInterval(intervalId);
    };
  }, [loadProjects, loadRuns, location.pathname, syncNotifications]);

  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void syncNotifications();
    }, 60_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [syncNotifications]);

  return (
    <div
      className="flex h-screen overflow-hidden selection:bg-emerald-500/30"
      style={{
        '--sidebar-width': sidebarCollapsed ? '5rem' : '16rem',
        '--app-header-height': '4rem',
      } as React.CSSProperties}
    >
      <a
        href="#main-content"
        className="sr-only focus:not-sr-only focus:absolute focus:top-4 focus:left-4 focus:z-50 focus:px-4 focus:py-2 focus:bg-emerald-600 focus:text-white focus:rounded-lg focus:shadow-lg"
      >
        Skip to main content
      </a>

      <Sidebar
        isCollapsed={sidebarCollapsed}
        onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <main
        id="main-content"
        role="main"
        aria-label="Main content"
        className="flex-1 flex flex-col relative overflow-hidden"
      >
        <Header
          isCollapsed={sidebarCollapsed}
          onToggle={() => setSidebarCollapsed(!sidebarCollapsed)}
        />

        <div className="flex-1 overflow-y-auto p-6 lg:p-10 z-10 custom-scrollbar scroll-smooth">
          <div className="max-w-7xl mx-auto">
            <Outlet />
          </div>
        </div>
      </main>
    </div>
  );
};
