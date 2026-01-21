# State Management Documentation

This directory contains all Zustand stores for the Digital Workforce Platform frontend.

## Overview

The application uses [Zustand](https://github.com/pmndrs/zustand) for state management. Zustand is a lightweight, fast, and scalable state management solution that provides a simple API with minimal boilerplate.

## Store Architecture

### Core Stores

1. **authStore.ts** - Authentication and session management
   - User authentication state
   - JWT token management
   - Persisted to localStorage

2. **userStore.ts** - User profile and resource quotas
   - User profile information
   - Resource quota tracking
   - Quota usage monitoring

3. **agentStore.ts** - Agent management
   - Agent list and status
   - Real-time agent updates via WebSocket
   - Agent filtering and search

4. **taskStore.ts** - Task and goal management
   - Goals and tasks tracking
   - Real-time task updates via WebSocket
   - Task filtering and search

5. **knowledgeStore.ts** - Knowledge base and documents
   - Document management
   - Upload queue tracking
   - Document filtering and search

6. **memoryStore.ts** - Memory system
   - Agent, company, and user context memories
   - Memory filtering by type, date, tags
   - Semantic search support

### UI Stores

7. **themeStore.ts** - Theme management
   - Light/dark/system theme
   - Persisted to localStorage

8. **preferencesStore.ts** - User preferences
   - Language selection
   - UI preferences (sidebar, layout)
   - Notification settings
   - Persisted to localStorage

9. **notificationStore.ts** - In-app notifications
   - Notification queue
   - Read/unread tracking
   - Notification panel state

## Usage Examples

### Basic Usage

```typescript
import { useAgentStore } from '@/stores';

function AgentList() {
  const { agents, isLoading, setStatusFilter } = useAgentStore();
  
  return (
    <div>
      {isLoading ? (
        <LoadingSpinner />
      ) : (
        agents.map(agent => <AgentCard key={agent.id} agent={agent} />)
      )}
    </div>
  );
}
```

### Computed Values

```typescript
import { useTaskStore } from '@/stores';

function TaskDashboard() {
  const getFilteredTasks = useTaskStore(state => state.getFilteredTasks);
  const filteredTasks = getFilteredTasks();
  
  return <TaskList tasks={filteredTasks} />;
}
```

### Real-time Updates

```typescript
import { useWebSocketSync } from '@/hooks/useWebSocketSync';
import { useAuthStore } from '@/stores';

function App() {
  const { token } = useAuthStore();
  const { isConnected } = useWebSocketSync(undefined, token);
  
  return (
    <div>
      <ConnectionIndicator connected={isConnected} />
      {/* Rest of app */}
    </div>
  );
}
```

### Store Synchronization

```typescript
import { useStoreSync } from '@/hooks/useStoreSync';

function Dashboard() {
  // Sync all stores on mount
  useStoreSync();
  
  return <DashboardContent />;
}

// Or sync specific stores
function AgentsPage() {
  useStoreSync({ syncAgents: true, syncTasks: false });
  
  return <AgentsList />;
}
```

### Manual Refresh

```typescript
import { useRefreshStore } from '@/hooks/useStoreSync';

function RefreshButton() {
  const { refreshAgents } = useRefreshStore();
  
  const handleRefresh = async () => {
    await refreshAgents();
  };
  
  return <button onClick={handleRefresh}>Refresh</button>;
}
```

## State Persistence

The following stores persist their state to localStorage:

- **authStore**: User and token (key: `auth-storage`)
- **themeStore**: Theme preference (key: `theme-storage`)
- **preferencesStore**: User preferences (key: `preferences-storage`)

Persisted state is automatically loaded on app initialization.

## WebSocket Integration

The `useWebSocketSync` hook automatically syncs WebSocket messages with stores:

- Agent status updates → `agentStore`
- Task status updates → `taskStore`
- Goal updates → `taskStore`
- System notifications → `notificationStore`

## Best Practices

### 1. Use Selectors for Performance

```typescript
// ❌ Bad - Re-renders on any store change
const store = useAgentStore();

// ✅ Good - Only re-renders when agents change
const agents = useAgentStore(state => state.agents);
```

### 2. Use Computed Functions

```typescript
// ✅ Use computed functions for derived state
const getFilteredAgents = useAgentStore(state => state.getFilteredAgents);
const filtered = getFilteredAgents();
```

### 3. Handle Loading and Error States

```typescript
const { agents, isLoading, error } = useAgentStore();

if (isLoading) return <LoadingSpinner />;
if (error) return <ErrorMessage message={error} />;
return <AgentList agents={agents} />;
```

### 4. Clear Errors After Handling

```typescript
const { error, clearError } = useAgentStore();

useEffect(() => {
  if (error) {
    toast.error(error);
    clearError();
  }
}, [error, clearError]);
```

### 5. Reset Stores on Logout

```typescript
import { resetAllStores } from '@/stores';

function LogoutButton() {
  const handleLogout = () => {
    resetAllStores();
    // Navigate to login
  };
  
  return <button onClick={handleLogout}>Logout</button>;
}
```

## Store Structure Pattern

Each store follows this consistent pattern:

```typescript
interface StoreState {
  // Data
  items: Item[];
  selectedItem: Item | null;
  
  // UI State
  isLoading: boolean;
  error: string | null;
  
  // Filters
  searchQuery: string;
  
  // Actions - CRUD
  setItems: (items: Item[]) => void;
  addItem: (item: Item) => void;
  updateItem: (id: string, updates: Partial<Item>) => void;
  removeItem: (id: string) => void;
  
  // Actions - UI
  setLoading: (loading: boolean) => void;
  setError: (error: string | null) => void;
  clearError: () => void;
  
  // Actions - Filters
  setSearchQuery: (query: string) => void;
  
  // Computed
  getFilteredItems: () => Item[];
  getItemById: (id: string) => Item | undefined;
  
  // Real-time
  handleItemUpdate: (update: any) => void;
  
  // Reset
  reset: () => void;
}
```

## Testing

Stores can be tested by accessing their state directly:

```typescript
import { useAgentStore } from '@/stores/agentStore';

describe('agentStore', () => {
  beforeEach(() => {
    useAgentStore.getState().reset();
  });
  
  it('should add an agent', () => {
    const store = useAgentStore.getState();
    const agent = { id: '1', name: 'Test Agent', /* ... */ };
    
    store.addAgent(agent);
    
    expect(store.agents).toHaveLength(1);
    expect(store.agents[0]).toEqual(agent);
  });
});
```

## Migration from Redux

If migrating from Redux, here are the key differences:

| Redux | Zustand |
|-------|---------|
| Actions + Reducers | Direct state updates |
| `useSelector` | `useStore(selector)` |
| `useDispatch` | Direct function calls |
| Provider required | No provider needed |
| Middleware for async | Async in actions |
| DevTools extension | Built-in DevTools |

## Performance Tips

1. **Use shallow equality for objects**: `useStore(state => state.obj, shallow)`
2. **Split large stores**: Keep stores focused on single domains
3. **Use computed functions**: Avoid deriving state in components
4. **Batch updates**: Zustand automatically batches React updates
5. **Use selectors**: Only subscribe to needed state slices

## Debugging

Enable Zustand DevTools:

```typescript
import { devtools } from 'zustand/middleware';

export const useAgentStore = create<AgentState>()(
  devtools(
    (set, get) => ({
      // ... store implementation
    }),
    { name: 'AgentStore' }
  )
);
```

Then use Redux DevTools extension to inspect state changes.

## Resources

- [Zustand Documentation](https://github.com/pmndrs/zustand)
- [Zustand Best Practices](https://github.com/pmndrs/zustand/wiki/Best-Practices)
- [TypeScript Guide](https://github.com/pmndrs/zustand/blob/main/docs/guides/typescript.md)
