import React, { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { notificationsApi } from '@/api/notifications';
import { useThemeStore } from '@/stores/themeStore';
import { useMissionStore } from '@/stores/missionStore';
import { useNotificationStore } from '@/stores/notificationStore';
import { buildWebSocketUrl } from '@/utils/runtimeUrls';

const NOTIFICATION_SYNC_EVENT_TYPES = new Set([
  'USER_CLARIFICATION_REQUESTED',
  'clarification_request',
  'MISSION_FAILED',
  'MISSION_COMPLETED',
  'QA_VERDICT',
]);

export const Layout: React.FC = () => {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const { applyTheme } = useThemeStore();
  const setGlobalMissionWsConnected = useMissionStore((state) => state.setGlobalMissionWsConnected);
  const isGlobalMissionWsConnected = useMissionStore((state) => state.isGlobalMissionWsConnected);
  const fetchMissions = useMissionStore((state) => state.fetchMissions);
  const replaceServerNotifications = useNotificationStore(
    (state) => state.replaceServerNotifications
  );
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

  // Apply theme on mount
  useEffect(() => {
    applyTheme();

    // Listen for system theme changes
    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleChange = () => {
      applyTheme();
    };

    mediaQuery.addEventListener('change', handleChange);
    return () => mediaQuery.removeEventListener('change', handleChange);
  }, [applyTheme]);

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyPress = (e: KeyboardEvent) => {
      // Ctrl/Cmd + B: Toggle sidebar
      if ((e.ctrlKey || e.metaKey) && e.key === 'b') {
        e.preventDefault();
        setSidebarCollapsed((prev) => !prev);
      }
    };

    window.addEventListener('keydown', handleKeyPress);
    return () => window.removeEventListener('keydown', handleKeyPress);
  }, []);

  // Keep layout CSS variables on :root so portal-based modals can resolve them.
  useEffect(() => {
    document.documentElement.style.setProperty(
      '--sidebar-width',
      sidebarCollapsed ? '5rem' : '16rem'
    );
    document.documentElement.style.setProperty('--app-header-height', '4rem');

    return () => {
      document.documentElement.style.removeProperty('--sidebar-width');
      document.documentElement.style.removeProperty('--app-header-height');
    };
  }, [sidebarCollapsed]);

  // Responsive: collapse sidebar on mobile
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

  // Global mission WS bridge:
  // - keep mission store in sync for mission card updates
  // - trigger notification center sync for user-facing event types
  useEffect(() => {
    let websocket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let notificationSyncTimer: number | null = null;
    let shouldReconnect = true;
    const scheduleNotificationSync = (delayMs = 300) => {
      if (notificationSyncTimer) {
        window.clearTimeout(notificationSyncTimer);
      }
      notificationSyncTimer = window.setTimeout(() => {
        void syncNotifications();
        notificationSyncTimer = null;
      }, delayMs);
    };

    const connect = () => {
      const wsUrl = buildWebSocketUrl('/missions');
      websocket = new WebSocket(wsUrl);
      websocket.onopen = () => {
        setGlobalMissionWsConnected(true);
        void fetchMissions();
        scheduleNotificationSync(0);
      };

      websocket.onmessage = (event) => {
        try {
          const message = JSON.parse(event.data) as {
            type?: string;
            data?: Record<string, unknown>;
          };
          if (message.type !== 'mission_event' || !message.data) return;

          const payload = message.data;
          const normalizedEvent = {
            event_id: String(payload.event_id || `ws-${Date.now()}`),
            mission_id: String(payload.mission_id || ''),
            event_type: String(payload.event_type || 'UNKNOWN'),
            agent_id: payload.agent_id ? String(payload.agent_id) : undefined,
            task_id: payload.task_id ? String(payload.task_id) : undefined,
            event_data:
              (payload.event_data as Record<string, unknown> | undefined) ||
              (payload.data as Record<string, unknown> | undefined),
            message: typeof payload.message === 'string' ? payload.message : undefined,
            created_at:
              typeof payload.created_at === 'string'
                ? payload.created_at
                : new Date().toISOString(),
          };

          useMissionStore.getState().handleMissionEvent(normalizedEvent);
          if (NOTIFICATION_SYNC_EVENT_TYPES.has(normalizedEvent.event_type)) {
            scheduleNotificationSync();
          }
        } catch {
          // Ignore malformed WS payloads.
        }
      };

      websocket.onerror = () => {
        websocket?.close();
      };

      websocket.onclose = () => {
        setGlobalMissionWsConnected(false);
        websocket = null;
        if (!shouldReconnect) return;
        reconnectTimer = window.setTimeout(() => {
          connect();
        }, 1500);
      };
    };

    connect();

    return () => {
      shouldReconnect = false;
      setGlobalMissionWsConnected(false);
      if (reconnectTimer) {
        window.clearTimeout(reconnectTimer);
      }
      if (notificationSyncTimer) {
        window.clearTimeout(notificationSyncTimer);
      }
      websocket?.close();
      websocket = null;
    };
  }, [fetchMissions, setGlobalMissionWsConnected, syncNotifications]);

  // Initial mission snapshot for notification fallback and mission card hydration.
  useEffect(() => {
    void fetchMissions();
    void syncNotifications();
  }, [fetchMissions, syncNotifications]);

  // Fallback polling only when global mission WS is disconnected.
  useEffect(() => {
    if (isGlobalMissionWsConnected) return;

    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void fetchMissions();
    }, 10_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [fetchMissions, isGlobalMissionWsConnected]);

  // Notification reconciliation:
  // - WS connected: low-frequency consistency sync
  // - WS disconnected: faster fallback sync
  useEffect(() => {
    const intervalId = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      void syncNotifications();
    }, isGlobalMissionWsConnected ? 180_000 : 15_000);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [isGlobalMissionWsConnected, syncNotifications]);

  return (
    <div 
      className="flex h-screen overflow-hidden selection:bg-emerald-500/30"
      style={{
        '--sidebar-width': sidebarCollapsed ? '5rem' : '16rem',
        '--app-header-height': '4rem',
      } as React.CSSProperties}
    >
      {/* Skip to main content link for keyboard navigation (6.9.2) */}
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
