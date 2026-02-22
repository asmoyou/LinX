/**
 * React Hook for WebSocket Connection
 * 
 * Provides a React-friendly interface to the WebSocket manager with:
 * - Automatic connection/disconnection on mount/unmount
 * - Connection status tracking
 * - Event subscription management
 * - Integration with authentication
 * 
 * References:
 * - Requirements 13, 15: Task Flow Visualization and API
 * - Task 6.12: WebSocket Real-Time Integration
 */

import { useEffect, useState, useCallback, useRef } from 'react';
import {
  WebSocketManager,
  getWebSocketManager,
  WebSocketStatus,
  WebSocketMessage,
  WebSocketMessageType,
  WebSocketEventHandler,
} from '../services/websocket';

export interface UseWebSocketOptions {
  url?: string;
  token?: string;
  autoConnect?: boolean;
  reconnect?: boolean;
  reconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
  debug?: boolean;
}

export interface UseWebSocketReturn {
  status: WebSocketStatus;
  isConnected: boolean;
  reconnectAttempts: number;
  lastHeartbeat: number;
  send: (message: WebSocketMessage | string) => boolean;
  connect: () => void;
  disconnect: () => void;
  on: (type: WebSocketMessageType | 'all', handler: WebSocketEventHandler) => () => void;
}

/**
 * Hook to manage WebSocket connection
 * 
 * @param options - WebSocket configuration options
 * @returns WebSocket connection state and methods
 * 
 * @example
 * ```tsx
 * const { status, isConnected, send, on } = useWebSocket({
 *   url: 'ws://localhost:8000/ws/tasks',
 *   token: authToken,
 *   autoConnect: true,
 * });
 * 
 * useEffect(() => {
 *   const unsubscribe = on('task_status_update', (message) => {
 *     console.log('Task updated:', message.data);
 *   });
 *   return unsubscribe;
 * }, [on]);
 * ```
 */
export function useWebSocket(options: UseWebSocketOptions = {}): UseWebSocketReturn {
  const {
    url = import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/tasks',
    token,
    autoConnect = true,
    reconnect = true,
    reconnectInterval = 1000,
    maxReconnectAttempts = 10,
    heartbeatInterval = 30000,
    debug = import.meta.env.DEV,
  } = options;

  const [status, setStatus] = useState<WebSocketStatus>('disconnected');
  const [reconnectAttempts, setReconnectAttempts] = useState(0);
  const [lastHeartbeat, setLastHeartbeat] = useState(0);
  const wsManagerRef = useRef<WebSocketManager | null>(null);
  const statusUpdateIntervalRef = useRef<ReturnType<typeof setInterval>>();

  // Initialize WebSocket manager
  useEffect(() => {
    if (!token) {
      console.warn('[useWebSocket] No authentication token provided');
      return;
    }

    try {
      wsManagerRef.current = getWebSocketManager({
        url,
        token,
        reconnect,
        reconnectInterval,
        maxReconnectAttempts,
        heartbeatInterval,
        debug,
      });

      // Subscribe to status changes
      const unsubscribe = wsManagerRef.current.onStatusChange((newStatus) => {
        setStatus(newStatus);
      });

      // Update reconnect attempts and heartbeat periodically
      statusUpdateIntervalRef.current = setInterval(() => {
        if (wsManagerRef.current) {
          setReconnectAttempts(wsManagerRef.current.getReconnectAttempts());
          setLastHeartbeat(wsManagerRef.current.getLastHeartbeatTime());
        }
      }, 1000);

      // Auto-connect if enabled
      if (autoConnect) {
        wsManagerRef.current.connect();
      }

      return () => {
        unsubscribe();
        if (statusUpdateIntervalRef.current) {
          clearInterval(statusUpdateIntervalRef.current);
        }
        if (wsManagerRef.current) {
          wsManagerRef.current.disconnect();
        }
      };
    } catch (err) {
      console.error('[useWebSocket] Failed to initialize WebSocket manager:', err);
    }
  }, [url, token, autoConnect, reconnect, reconnectInterval, maxReconnectAttempts, heartbeatInterval, debug]);

  // Send message
  const send = useCallback((message: WebSocketMessage | string): boolean => {
    if (!wsManagerRef.current) {
      console.warn('[useWebSocket] WebSocket manager not initialized');
      return false;
    }
    return wsManagerRef.current.send(message);
  }, []);

  // Connect
  const connect = useCallback(() => {
    if (!wsManagerRef.current) {
      console.warn('[useWebSocket] WebSocket manager not initialized');
      return;
    }
    wsManagerRef.current.connect();
  }, []);

  // Disconnect
  const disconnect = useCallback(() => {
    if (!wsManagerRef.current) {
      console.warn('[useWebSocket] WebSocket manager not initialized');
      return;
    }
    wsManagerRef.current.disconnect();
  }, []);

  // Subscribe to events
  const on = useCallback((type: WebSocketMessageType | 'all', handler: WebSocketEventHandler) => {
    if (!wsManagerRef.current) {
      console.warn('[useWebSocket] WebSocket manager not initialized');
      return () => {};
    }
    return wsManagerRef.current.on(type, handler);
  }, []);

  return {
    status,
    isConnected: status === 'connected',
    reconnectAttempts,
    lastHeartbeat,
    send,
    connect,
    disconnect,
    on,
  };
}

/**
 * Hook to subscribe to specific WebSocket message type
 * 
 * @param type - Message type to subscribe to
 * @param handler - Event handler function
 * @param deps - Dependencies array for handler
 * 
 * @example
 * ```tsx
 * useWebSocketEvent('task_status_update', (message) => {
 *   console.log('Task updated:', message.data);
 * }, []);
 * ```
 */
export function useWebSocketEvent(
  type: WebSocketMessageType | 'all',
  handler: WebSocketEventHandler,
  deps: React.DependencyList = []
): void {
  const wsManagerRef = useRef<WebSocketManager | null>(null);

  useEffect(() => {
    try {
      wsManagerRef.current = getWebSocketManager();
      const unsubscribe = wsManagerRef.current.on(type, handler);
      return unsubscribe;
    } catch {
      console.error('[useWebSocketEvent] WebSocket manager not initialized');
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [type, ...deps]);
}
