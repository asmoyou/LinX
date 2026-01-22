# WebSocket Real-Time Integration

This directory contains the WebSocket implementation for real-time updates in the LinX platform.

## Overview

The WebSocket system provides real-time bidirectional communication between the frontend and backend, enabling:

- Real-time task status updates
- Agent status monitoring
- System notifications
- Metrics updates
- Task flow visualization

## Architecture

### Components

1. **WebSocketManager** (`websocket.ts`)
   - Core WebSocket connection manager
   - Handles connection lifecycle
   - Implements automatic reconnection with exponential backoff
   - Provides heartbeat mechanism
   - Event-based message handling

2. **useWebSocket Hook** (`../hooks/useWebSocket.ts`)
   - React hook for WebSocket integration
   - Manages connection state
   - Provides React-friendly API
   - Handles cleanup on unmount

3. **useWebSocketSync Hook** (`../hooks/useWebSocketSync.ts`)
   - Syncs WebSocket messages with Zustand stores
   - Automatically updates agent, task, and notification stores
   - Handles all message types

4. **WebSocketStatus Component** (`../components/WebSocketStatus.tsx`)
   - Visual connection status indicator
   - Shows connection state with icons and colors
   - Displays reconnection attempts

## Features

### Automatic Reconnection

The WebSocket manager automatically attempts to reconnect when the connection is lost:

- **Exponential Backoff**: Delay increases with each attempt (1s, 1.5s, 2.25s, ...)
- **Max Attempts**: Configurable maximum reconnection attempts (default: 10)
- **Max Interval**: Maximum delay between attempts (default: 30s)

### Heartbeat Mechanism

Keeps the connection alive and detects dead connections:

- **Interval**: Sends heartbeat every 30 seconds (configurable)
- **Timeout**: Closes connection if no response within 5 seconds
- **Automatic**: Starts on connection, stops on disconnection

### Authentication

WebSocket connections are authenticated using JWT tokens:

- Token passed as query parameter: `ws://host/path?token=<jwt>`
- Token automatically included from authentication state
- Connection rejected if token is invalid

### Message Types

The system supports the following message types:

#### Agent Updates
- `agent_status_update`: Agent status changed
- `agent_created`: New agent created
- `agent_deleted`: Agent deleted

#### Task Updates
- `task_status_update`: Task status changed
- `task_created`: New task created
- `task_completed`: Task completed successfully
- `task_failed`: Task failed with error
- `goal_status_update`: Goal status changed

#### Task Flow
- `task_flow_initial`: Initial task flow graph
- `task_flow_update`: Task flow graph updated
- `node_update`: Task node updated
- `relationship_added`: New task relationship

#### System
- `system_notification`: System notification
- `metrics_update`: System metrics updated
- `heartbeat`: Heartbeat ping
- `pong`: Heartbeat response

## Usage

### Basic Usage

```tsx
import { useWebSocket } from '../hooks/useWebSocket';

function MyComponent() {
  const { status, isConnected, send, on } = useWebSocket({
    url: 'ws://localhost:8000/ws/tasks',
    token: authToken,
    autoConnect: true,
  });

  useEffect(() => {
    const unsubscribe = on('task_status_update', (message) => {
      console.log('Task updated:', message.data);
    });
    return unsubscribe;
  }, [on]);

  return (
    <div>
      <p>Status: {status}</p>
      <p>Connected: {isConnected ? 'Yes' : 'No'}</p>
    </div>
  );
}
```

### Store Synchronization

```tsx
import { useWebSocketSync } from '../hooks/useWebSocketSync';

function App() {
  const { isConnected } = useWebSocketSync(
    'ws://localhost:8000/ws/tasks',
    authToken
  );

  return (
    <div>
      {/* Your app content */}
      {/* Stores are automatically updated */}
    </div>
  );
}
```

### Connection Status Indicator

```tsx
import { WebSocketStatus } from '../components/WebSocketStatus';

function Header() {
  return (
    <header>
      <h1>LinX Platform</h1>
      <WebSocketStatus showText showReconnectAttempts />
    </header>
  );
}
```

### Subscribing to Specific Events

```tsx
import { useWebSocketEvent } from '../hooks/useWebSocket';

function TaskList() {
  useWebSocketEvent('task_completed', (message) => {
    toast.success(`Task ${message.data.title} completed!`);
  }, []);

  return <div>{/* Task list */}</div>;
}
```

## Configuration

### WebSocket Manager Options

```typescript
interface WebSocketConfig {
  url: string;                    // WebSocket URL
  token?: string;                 // Authentication token
  reconnect?: boolean;            // Enable auto-reconnect (default: true)
  reconnectInterval?: number;     // Initial reconnect delay (default: 1000ms)
  reconnectDecay?: number;        // Backoff multiplier (default: 1.5)
  maxReconnectInterval?: number;  // Max reconnect delay (default: 30000ms)
  maxReconnectAttempts?: number;  // Max reconnect attempts (default: 10)
  heartbeatInterval?: number;     // Heartbeat interval (default: 30000ms)
  heartbeatTimeout?: number;      // Heartbeat timeout (default: 5000ms)
  debug?: boolean;                // Enable debug logging (default: false)
}
```

### Environment Variables

```env
# WebSocket URL
VITE_WS_URL=ws://localhost:8000/ws/tasks

# For production
VITE_WS_URL=wss://api.example.com/ws/tasks
```

## Error Handling

### Connection Errors

The manager handles various connection errors:

1. **Network Errors**: Automatic reconnection with backoff
2. **Authentication Errors**: Connection rejected, no reconnection
3. **Timeout Errors**: Connection closed, automatic reconnection
4. **Max Attempts**: Shows error notification to user

### Message Errors

Invalid messages are logged but don't affect the connection:

```typescript
try {
  const message = JSON.parse(event.data);
  handleMessage(message);
} catch (error) {
  console.error('Failed to parse message:', error);
  // Connection remains open
}
```

## Testing

### Unit Tests

Run WebSocket manager tests:

```bash
npm test websocket.test.ts
```

### Integration Tests

Test WebSocket with backend:

```bash
# Start backend
cd backend
uvicorn api_gateway.main:app --reload

# Start frontend
cd frontend
npm run dev

# Open browser and check console for WebSocket logs
```

### Manual Testing

1. Open browser DevTools → Network → WS
2. Connect to application
3. Verify WebSocket connection established
4. Check messages being sent/received
5. Test reconnection by stopping backend

## Backend Integration

### Backend WebSocket Endpoint

The backend provides WebSocket endpoints at:

- `/ws/tasks` - General task updates
- `/ws/tasks/{task_id}/flow` - Task flow visualization

### Message Format

All messages follow this format:

```json
{
  "type": "message_type",
  "data": {
    // Message-specific data
  },
  "timestamp": "2024-01-01T00:00:00Z"
}
```

### Broadcasting Updates

Backend broadcasts updates using:

```python
from api_gateway.websocket import broadcast_task_update

await broadcast_task_update(user_id, {
    "type": "task_status_update",
    "data": {
        "task_id": task_id,
        "status": "completed",
        "progress": 100
    }
})
```

## Performance Considerations

### Connection Pooling

- Single WebSocket connection per user session
- Multiplexed message types over one connection
- Reduces overhead compared to multiple connections

### Message Batching

For high-frequency updates, consider batching:

```typescript
// Backend batches updates every 100ms
const updates = [];
setInterval(() => {
  if (updates.length > 0) {
    broadcast({ type: 'batch_update', data: updates });
    updates.length = 0;
  }
}, 100);
```

### Memory Management

- Event handlers automatically cleaned up on unmount
- Connection closed when component unmounts
- Singleton manager prevents multiple instances

## Security

### Authentication

- JWT token required for connection
- Token validated on connection
- Invalid tokens rejected immediately

### Message Validation

- All messages validated on backend
- Type checking on frontend
- Unknown message types logged and ignored

### Rate Limiting

Backend implements rate limiting:

- Max messages per second per connection
- Automatic throttling for excessive messages
- Connection closed if limits exceeded

## Troubleshooting

### Connection Not Establishing

1. Check WebSocket URL in environment variables
2. Verify authentication token is valid
3. Check browser console for errors
4. Verify backend WebSocket endpoint is running

### Messages Not Received

1. Check message type subscription
2. Verify message handler is registered
3. Check browser DevTools → Network → WS for messages
4. Verify backend is broadcasting messages

### Frequent Reconnections

1. Check network stability
2. Verify heartbeat configuration
3. Check backend logs for connection issues
4. Increase heartbeat timeout if needed

### High Memory Usage

1. Verify event handlers are cleaned up
2. Check for memory leaks in message handlers
3. Limit number of stored messages
4. Implement message pruning

## Future Enhancements

- [ ] Message compression (gzip)
- [ ] Binary message support (Protocol Buffers)
- [ ] Message queuing for offline support
- [ ] Selective subscription (subscribe to specific channels)
- [ ] Message acknowledgment and retry
- [ ] Connection quality metrics
- [ ] Automatic quality adjustment based on network

## References

- [WebSocket API (MDN)](https://developer.mozilla.org/en-US/docs/Web/API/WebSocket)
- [FastAPI WebSockets](https://fastapi.tiangolo.com/advanced/websockets/)
- [Requirements 13, 15](../../.kiro/specs/digital-workforce-platform/requirements.md)
- [Task 6.12](../../.kiro/specs/digital-workforce-platform/tasks.md)
