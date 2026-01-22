import { useEffect } from 'react';
import { useAgentStore } from '../stores/agentStore';
import { useTaskStore } from '../stores/taskStore';
import { useNotificationStore } from '../stores/notificationStore';
import { useWebSocket } from './useWebSocket';
import type { WebSocketMessage } from '../services/websocket';

/**
 * Hook to sync WebSocket updates with Zustand stores
 * 
 * This hook listens to WebSocket messages and automatically updates
 * the relevant stores with real-time data. It uses the new WebSocket
 * manager for improved reliability and features.
 * 
 * @param wsUrl - WebSocket URL (optional, defaults to env variable)
 * @param token - Authentication token
 */
export const useWebSocketSync = (wsUrl?: string, token?: string) => {
  const agentStore = useAgentStore();
  const taskStore = useTaskStore();
  const notificationStore = useNotificationStore();

  const { status, isConnected, reconnectAttempts, on } = useWebSocket({
    url: wsUrl,
    token,
    autoConnect: true,
    reconnect: true,
    maxReconnectAttempts: 10,
    debug: import.meta.env.DEV,
  });

  // Define message handler
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

  // Subscribe to all WebSocket messages
  useEffect(() => {
    const unsubscribe = on('all', handleWebSocketMessage);
    return unsubscribe;
  }, [on, handleWebSocketMessage]);

  // Show notification when max reconnect attempts reached
  useEffect(() => {
    if (status === 'error' && reconnectAttempts >= 10) {
      notificationStore.addNotification({
        type: 'error',
        title: 'Connection Lost',
        message: 'Unable to connect to real-time updates. Please refresh the page.',
      });
    }
  }, [status, reconnectAttempts, notificationStore]);

  // Show notification when max reconnect attempts reached
  useEffect(() => {
    if (status === 'error' && reconnectAttempts >= 10) {
      notificationStore.addNotification({
        type: 'error',
        title: 'Connection Lost',
        message: 'Unable to connect to real-time updates. Please refresh the page.',
      });
    }
  }, [status, reconnectAttempts, notificationStore]);

  return {
    isConnected,
    status,
    reconnectAttempts,
  };
};
