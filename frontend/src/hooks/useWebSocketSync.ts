import { useEffect, useRef } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { useTaskStore } from '../stores/taskStore';
import { useNotificationStore } from '../stores/notificationStore';

/**
 * WebSocket message types from backend
 */
type WebSocketMessageType =
  | 'agent_status_update'
  | 'task_status_update'
  | 'goal_status_update'
  | 'system_notification'
  | 'agent_created'
  | 'agent_deleted'
  | 'task_created'
  | 'task_completed'
  | 'task_failed';

interface WebSocketMessage {
  type: WebSocketMessageType;
  data: any;
  timestamp: string;
}

/**
 * Hook to sync WebSocket updates with Zustand stores
 * 
 * This hook listens to WebSocket messages and automatically updates
 * the relevant stores with real-time data.
 * 
 * @param wsUrl - WebSocket URL (optional, defaults to env variable)
 * @param token - Authentication token
 */
export const useWebSocketSync = (wsUrl?: string, token?: string) => {
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<ReturnType<typeof setTimeout>>();
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 3000;

  const agentStore = useAgentStore();
  const taskStore = useTaskStore();
  const notificationStore = useNotificationStore();

  useEffect(() => {
    if (!token) {
      console.warn('WebSocket: No authentication token provided');
      return;
    }

    const url = wsUrl || import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws';
    const wsUrlWithToken = `${url}?token=${token}`;

    const connect = () => {
      try {
        console.log('WebSocket: Connecting...');
        const ws = new WebSocket(wsUrlWithToken);
        wsRef.current = ws;

        ws.onopen = () => {
          console.log('WebSocket: Connected');
          reconnectAttemptsRef.current = 0;
          
          // Send initial subscription message
          ws.send(JSON.stringify({
            type: 'subscribe',
            channels: ['agents', 'tasks', 'notifications'],
          }));
        };

        ws.onmessage = (event) => {
          try {
            const message: WebSocketMessage = JSON.parse(event.data);
            handleWebSocketMessage(message);
          } catch (error) {
            console.error('WebSocket: Failed to parse message', error);
          }
        };

        ws.onerror = (error) => {
          console.error('WebSocket: Error', error);
        };

        ws.onclose = (event) => {
          console.log('WebSocket: Disconnected', event.code, event.reason);
          wsRef.current = null;

          // Attempt to reconnect
          if (reconnectAttemptsRef.current < maxReconnectAttempts) {
            reconnectAttemptsRef.current++;
            console.log(
              `WebSocket: Reconnecting (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})...`
            );
            reconnectTimeoutRef.current = setTimeout(connect, reconnectDelay);
          } else {
            console.error('WebSocket: Max reconnection attempts reached');
            notificationStore.addNotification({
              type: 'error',
              title: 'Connection Lost',
              message: 'Unable to connect to real-time updates. Please refresh the page.',
            });
          }
        };
      } catch (error) {
        console.error('WebSocket: Connection failed', error);
      }
    };

    connect();

    // Cleanup on unmount
    return () => {
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [token, wsUrl, agentStore, taskStore, notificationStore]);

  const handleWebSocketMessage = (message: WebSocketMessage) => {
    console.log('WebSocket: Received message', message.type);

    switch (message.type) {
      case 'agent_status_update':
        agentStore.handleAgentUpdate({
          id: message.data.agent_id,
          updates: {
            status: message.data.status,
            currentTask: message.data.current_task,
          },
        });
        break;

      case 'agent_created':
        agentStore.addAgent(message.data);
        notificationStore.addNotification({
          type: 'info',
          title: 'Agent Created',
          message: `Agent "${message.data.name}" has been created`,
        });
        break;

      case 'agent_deleted':
        agentStore.removeAgent(message.data.agent_id);
        notificationStore.addNotification({
          type: 'info',
          title: 'Agent Deleted',
          message: `Agent has been removed`,
        });
        break;

      case 'task_status_update':
        taskStore.handleTaskUpdate({
          id: message.data.task_id,
          updates: {
            status: message.data.status,
            progress: message.data.progress,
            result: message.data.result,
            error: message.data.error,
          },
        });
        break;

      case 'goal_status_update':
        taskStore.handleGoalUpdate({
          id: message.data.goal_id,
          updates: {
            status: message.data.status,
            clarificationNeeded: message.data.clarification_needed,
            clarificationQuestions: message.data.clarification_questions,
          },
        });
        break;

      case 'task_created':
        taskStore.addTask(message.data);
        break;

      case 'task_completed':
        taskStore.handleTaskUpdate({
          id: message.data.task_id,
          updates: {
            status: 'completed',
            progress: 100,
            result: message.data.result,
            endTime: message.data.completed_at,
          },
        });
        notificationStore.addNotification({
          type: 'success',
          title: 'Task Completed',
          message: `Task "${message.data.title}" has been completed`,
          actionUrl: `/tasks/${message.data.task_id}`,
          actionLabel: 'View',
        });
        break;

      case 'task_failed':
        taskStore.handleTaskUpdate({
          id: message.data.task_id,
          updates: {
            status: 'failed',
            error: message.data.error,
            endTime: message.data.failed_at,
          },
        });
        notificationStore.addNotification({
          type: 'error',
          title: 'Task Failed',
          message: `Task "${message.data.title}" has failed: ${message.data.error}`,
          actionUrl: `/tasks/${message.data.task_id}`,
          actionLabel: 'View',
        });
        break;

      case 'system_notification':
        notificationStore.addNotification({
          type: message.data.type || 'info',
          title: message.data.title,
          message: message.data.message,
          actionUrl: message.data.action_url,
          actionLabel: message.data.action_label,
        });
        break;

      default:
        console.warn('WebSocket: Unknown message type', message.type);
    }
  };

  return {
    isConnected: wsRef.current?.readyState === WebSocket.OPEN,
    reconnectAttempts: reconnectAttemptsRef.current,
  };
};
