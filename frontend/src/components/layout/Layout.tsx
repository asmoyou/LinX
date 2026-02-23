import React, { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { Header } from './Header';
import { useThemeStore } from '@/stores/themeStore';
import { useMissionStore } from '@/stores/missionStore';
import { useNotificationStore } from '@/stores/notificationStore';

export const Layout: React.FC = () => {
  const [sidebarCollapsed, setSidebarCollapsed] = React.useState(false);
  const { applyTheme } = useThemeStore();
  const setGlobalMissionWsConnected = useMissionStore((state) => state.setGlobalMissionWsConnected);
  const isGlobalMissionWsConnected = useMissionStore((state) => state.isGlobalMissionWsConnected);
  const fetchMissions = useMissionStore((state) => state.fetchMissions);
  const missions = useMissionStore((state) => state.missions);
  const addNotification = useNotificationStore((state) => state.addNotification);
  const seenNotificationEventIdsRef = React.useRef<Set<string>>(new Set());
  const clarificationNotificationKeyRef = React.useRef<Set<string>>(new Set());

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
  // - push clarification requests into the notification center
  useEffect(() => {
    let websocket: WebSocket | null = null;
    let reconnectTimer: number | null = null;
    let shouldReconnect = true;

    const connect = () => {
      const configuredWsBase =
        (import.meta.env.VITE_WS_URL as string | undefined)?.trim() || '';
      const configuredApiBase =
        (import.meta.env.VITE_API_URL as string | undefined)?.trim() || '/api/v1';
      const normalizedApiBase = configuredApiBase.startsWith('/')
        ? configuredApiBase
        : `/${configuredApiBase}`;
      const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';

      const wsBase = configuredWsBase
        ? configuredWsBase.replace(/\/$/, '')
        : configuredApiBase.startsWith('http')
          ? `${configuredApiBase.replace(/^http/, 'ws').replace(/\/$/, '')}/ws`
          : import.meta.env.DEV
            ? `${wsProtocol}://${window.location.hostname}:8000${normalizedApiBase}/ws`
            : `${window.location.origin.replace(/^http/, 'ws')}${normalizedApiBase}/ws`;

      const wsUrl = `${wsBase}/missions`;
      websocket = new WebSocket(wsUrl);
      websocket.onopen = () => {
        setGlobalMissionWsConnected(true);
        void fetchMissions();
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

          if (
            (normalizedEvent.event_type === 'USER_CLARIFICATION_REQUESTED' ||
              normalizedEvent.event_type === 'clarification_request') &&
            normalizedEvent.mission_id
          ) {
            if (seenNotificationEventIdsRef.current.has(normalizedEvent.event_id)) {
              return;
            }
            seenNotificationEventIdsRef.current.add(normalizedEvent.event_id);
            if (seenNotificationEventIdsRef.current.size > 2000) {
              seenNotificationEventIdsRef.current.clear();
              seenNotificationEventIdsRef.current.add(normalizedEvent.event_id);
            }

            const question =
              typeof normalizedEvent.event_data?.questions === 'string'
                ? normalizedEvent.event_data.questions.trim()
                : normalizedEvent.message || '';
            const preview = question.length > 120 ? `${question.slice(0, 120)}...` : question;
            const shortId = normalizedEvent.mission_id.slice(0, 8);
            const dedupeKey = `${normalizedEvent.mission_id}:${normalizedEvent.created_at || normalizedEvent.event_id}`;
            clarificationNotificationKeyRef.current.add(dedupeKey);
            if (clarificationNotificationKeyRef.current.size > 4000) {
              clarificationNotificationKeyRef.current.clear();
              clarificationNotificationKeyRef.current.add(dedupeKey);
            }

            addNotification({
              type: 'warning',
              title: `任务 ${shortId} 需要澄清`,
              message: preview || '请补充任务澄清信息以继续执行。',
              actionUrl: `/tasks?missionId=${normalizedEvent.mission_id}&focus=clarification`,
              actionLabel: '去处理',
            });
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
      websocket?.close();
      websocket = null;
    };
  }, [addNotification, fetchMissions, setGlobalMissionWsConnected]);

  // Initial mission snapshot for notification fallback and mission card hydration.
  useEffect(() => {
    void fetchMissions();
  }, [fetchMissions]);

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

  // Notification fallback for pending clarification missions.
  // This covers disconnections and page reloads where WS events were missed.
  useEffect(() => {
    for (const mission of missions) {
      const pendingCount = Math.max(0, mission.pending_clarification_count ?? 0);
      if (!mission.needs_clarification || pendingCount <= 0) continue;

      const marker =
        mission.latest_clarification_requested_at ||
        String(mission.updated_at || '') ||
        String(pendingCount);
      const dedupeKey = `${mission.mission_id}:${marker}`;
      if (clarificationNotificationKeyRef.current.has(dedupeKey)) continue;

      clarificationNotificationKeyRef.current.add(dedupeKey);
      if (clarificationNotificationKeyRef.current.size > 4000) {
        clarificationNotificationKeyRef.current.clear();
        clarificationNotificationKeyRef.current.add(dedupeKey);
      }

      const preview =
        typeof mission.latest_clarification_request === 'string'
          ? mission.latest_clarification_request.trim()
          : '';
      const message = preview.length > 0 ? preview : '请补充任务澄清信息以继续执行。';
      addNotification({
        type: 'warning',
        title: `任务 ${mission.mission_id.slice(0, 8)} 需要澄清`,
        message: message.length > 120 ? `${message.slice(0, 120)}...` : message,
        actionUrl: `/tasks?missionId=${mission.mission_id}&focus=clarification`,
        actionLabel: '去处理',
      });
    }
  }, [addNotification, missions]);

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
        <div className="absolute inset-0 scan-line pointer-events-none"></div>
        
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
