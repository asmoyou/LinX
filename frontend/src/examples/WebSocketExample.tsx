/**
 * WebSocket Integration Example
 * 
 * This file demonstrates how to use the WebSocket system in your components.
 * 
 * References:
 * - Task 6.12: WebSocket Real-Time Integration
 */

import { useEffect } from 'react';
import { useWebSocket, useWebSocketEvent } from '../hooks/useWebSocket';
import { useWebSocketSync } from '../hooks/useWebSocketSync';
import { WebSocketStatus, WebSocketStatusCompact } from '../components/WebSocketStatus';

/**
 * Example 1: Basic WebSocket Connection
 * 
 * Shows how to connect to WebSocket and display connection status
 */
export function BasicWebSocketExample() {
  const { status, isConnected, reconnectAttempts } = useWebSocket({
    url: 'ws://localhost:8000/ws/tasks',
    token: 'your-jwt-token',
    autoConnect: true,
  });

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-4">WebSocket Connection</h2>
      
      {/* Full status indicator */}
      <WebSocketStatus showText showReconnectAttempts />
      
      <div className="mt-4 space-y-2">
        <p>Status: {status}</p>
        <p>Connected: {isConnected ? 'Yes' : 'No'}</p>
        <p>Reconnect Attempts: {reconnectAttempts}</p>
      </div>
    </div>
  );
}

/**
 * Example 2: Listening to Specific Events
 * 
 * Shows how to subscribe to specific WebSocket message types
 */
export function EventListenerExample() {
  const { on } = useWebSocket({
    url: 'ws://localhost:8000/ws/tasks',
    token: 'your-jwt-token',
    autoConnect: true,
  });

  useEffect(() => {
    // Subscribe to task status updates
    const unsubscribe = on('task_status_update', (message) => {
      console.log('Task updated:', message.data);
      // Handle task update
    });

    // Cleanup subscription on unmount
    return unsubscribe;
  }, [on]);

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-4">Event Listener</h2>
      <p>Check console for task updates</p>
    </div>
  );
}

/**
 * Example 3: Using the Event Hook
 * 
 * Shows how to use the useWebSocketEvent hook for cleaner code
 */
export function EventHookExample() {
  // Subscribe to task completed events
  useWebSocketEvent('task_completed', (message) => {
    console.log('Task completed:', message.data);
    // Show notification, update UI, etc.
  }, []);

  // Subscribe to agent status updates
  useWebSocketEvent('agent_status_update', (message) => {
    console.log('Agent status changed:', message.data);
  }, []);

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-4">Event Hook Example</h2>
      <p>Listening to task and agent events</p>
    </div>
  );
}

/**
 * Example 4: Automatic Store Synchronization
 * 
 * Shows how to use useWebSocketSync for automatic store updates
 */
export function StoreSyncExample() {
  const { isConnected } = useWebSocketSync(
    'ws://localhost:8000/ws/tasks',
    'your-jwt-token'
  );

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-4">Store Synchronization</h2>
      <p>Connection: {isConnected ? 'Active' : 'Inactive'}</p>
      <p className="mt-2 text-sm text-gray-600">
        Agent, task, and notification stores are automatically updated
      </p>
    </div>
  );
}

/**
 * Example 5: Header with Status Indicator
 * 
 * Shows how to add WebSocket status to your app header
 */
export function HeaderWithStatus() {
  return (
    <header className="flex items-center justify-between p-4 bg-white dark:bg-gray-800 border-b">
      <h1 className="text-2xl font-bold">LinX Platform</h1>
      
      <div className="flex items-center gap-4">
        {/* Compact status indicator */}
        <WebSocketStatusCompact />
        
        {/* User menu, etc. */}
      </div>
    </header>
  );
}

/**
 * Example 6: Sending Messages
 * 
 * Shows how to send messages to the server
 */
export function SendMessageExample() {
  const { send, isConnected } = useWebSocket({
    url: 'ws://localhost:8000/ws/tasks',
    token: 'your-jwt-token',
    autoConnect: true,
  });

  const handleRefresh = () => {
    if (isConnected) {
      send({
        type: 'task_status_update',
        data: { action: 'refresh' },
      });
    }
  };

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-4">Send Message</h2>
      <button
        onClick={handleRefresh}
        disabled={!isConnected}
        className="px-4 py-2 bg-blue-500 text-white rounded disabled:opacity-50"
      >
        Refresh Tasks
      </button>
    </div>
  );
}

/**
 * Example 7: Complete App Integration
 * 
 * Shows how to integrate WebSocket into your main App component
 */
export function AppWithWebSocket() {
  // Initialize WebSocket with automatic store sync
  const { isConnected } = useWebSocketSync(
    import.meta.env.VITE_WS_URL || 'ws://localhost:8000/ws/tasks',
    'your-jwt-token' // Get from auth context
  );

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
      {/* Header with status */}
      <header className="flex items-center justify-between p-4 bg-white dark:bg-gray-800 border-b">
        <h1 className="text-2xl font-bold">LinX Platform</h1>
        <WebSocketStatus showText={false} />
      </header>

      {/* Main content */}
      <main className="container mx-auto p-4">
        {!isConnected && (
          <div className="bg-yellow-50 dark:bg-yellow-900/20 border border-yellow-200 dark:border-yellow-800 rounded-lg p-4 mb-4">
            <p className="text-yellow-800 dark:text-yellow-200">
              Real-time updates are currently unavailable. Reconnecting...
            </p>
          </div>
        )}

        {/* Your app content */}
        <div>
          {/* Dashboard, tasks, agents, etc. */}
        </div>
      </main>
    </div>
  );
}

/**
 * Example 8: Manual Connection Control
 * 
 * Shows how to manually control the WebSocket connection
 */
export function ManualConnectionExample() {
  const { status, connect, disconnect } = useWebSocket({
    url: 'ws://localhost:8000/ws/tasks',
    token: 'your-jwt-token',
    autoConnect: false, // Don't auto-connect
  });

  return (
    <div className="p-4">
      <h2 className="text-xl font-bold mb-4">Manual Connection</h2>
      
      <div className="flex gap-2">
        <button
          onClick={connect}
          disabled={status === 'connected' || status === 'connecting'}
          className="px-4 py-2 bg-green-500 text-white rounded disabled:opacity-50"
        >
          Connect
        </button>
        
        <button
          onClick={disconnect}
          disabled={status === 'disconnected'}
          className="px-4 py-2 bg-red-500 text-white rounded disabled:opacity-50"
        >
          Disconnect
        </button>
      </div>

      <p className="mt-4">Status: {status}</p>
    </div>
  );
}
