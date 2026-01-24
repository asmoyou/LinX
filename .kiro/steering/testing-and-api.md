# Testing and API Client Rules

## Critical Principles

1. **ALWAYS use apiClient for API calls** - Never use raw fetch() or axios directly
2. **ALWAYS write unit tests** - Every feature must have corresponding tests
3. **ALWAYS update tests when modifying features** - Tests must stay in sync with code
4. **Tests are NOT optional** - They are a required part of every implementation

## Frontend API Client Rules

### ❌ NEVER Do This

```typescript
// ❌ BAD: Direct fetch calls
const response = await fetch('/api/agents');
const data = await response.json();

// ❌ BAD: Direct axios calls
const response = await axios.get('/api/agents');

// ❌ BAD: Inline API logic in components
function AgentList() {
  const [agents, setAgents] = useState([]);
  
  useEffect(() => {
    fetch('/api/agents')
      .then(res => res.json())
      .then(setAgents);
  }, []);
}
```

### ✅ ALWAYS Do This

```typescript
// ✅ GOOD: Use apiClient wrapper
import { apiClient } from '@/api/client';

const response = await apiClient.get('/agents');
const data = response.data;

// ✅ GOOD: Use typed API functions
import { agentApi } from '@/api/agents';

const agents = await agentApi.getAll();
const agent = await agentApi.getById(id);
await agentApi.create(agentData);
await agentApi.update(id, updates);
await agentApi.delete(id);

// ✅ GOOD: Use in components
function AgentList() {
  const [agents, setAgents] = useState<Agent[]>([]);
  
  useEffect(() => {
    agentApi.getAll()
      .then(setAgents)
      .catch(handleError);
  }, []);
}
```

## API Client Structure

### File Organization

```
frontend/src/api/
├── client.ts           # Base apiClient configuration
├── types.ts            # Shared API types
├── agents.ts           # Agent API functions
├── tasks.ts            # Task API functions
├── llm.ts              # LLM API functions
├── knowledge.ts        # Knowledge base API functions
└── auth.ts             # Authentication API functions
```

### Base Client Configuration

Location: `frontend/src/api/client.ts`

```typescript
import axios, { AxiosInstance, AxiosError } from 'axios';

// Create base client with default configuration
export const apiClient: AxiosInstance = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000/api/v1',
  timeout: 30000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor - Add auth token
apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('auth_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Response interceptor - Handle errors globally
apiClient.interceptors.response.use(
  (response) => response,
  (error: AxiosError) => {
    if (error.response?.status === 401) {
      // Handle unauthorized - redirect to login
      localStorage.removeItem('auth_token');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

### API Module Pattern

Each API module should follow this pattern:

```typescript
// frontend/src/api/agents.ts
import { apiClient } from './client';
import type { Agent, CreateAgentRequest, UpdateAgentRequest } from './types';

export const agentApi = {
  /**
   * Get all agents
   */
  async getAll(): Promise<Agent[]> {
    const response = await apiClient.get<Agent[]>('/agents');
    return response.data;
  },

  /**
   * Get agent by ID
   */
  async getById(id: string): Promise<Agent> {
    const response = await apiClient.get<Agent>(`/agents/${id}`);
    return response.data;
  },

  /**
   * Create new agent
   */
  async create(data: CreateAgentRequest): Promise<Agent> {
    const response = await apiClient.post<Agent>('/agents', data);
    return response.data;
  },

  /**
   * Update agent
   */
  async update(id: string, data: UpdateAgentRequest): Promise<Agent> {
    const response = await apiClient.put<Agent>(`/agents/${id}`, data);
    return response.data;
  },

  /**
   * Delete agent
   */
  async delete(id: string): Promise<void> {
    await apiClient.delete(`/agents/${id}`);
  },

  /**
   * Get agent status
   */
  async getStatus(id: string): Promise<{ status: string; details: any }> {
    const response = await apiClient.get(`/agents/${id}/status`);
    return response.data;
  },
};
```

### Type Definitions

Location: `frontend/src/api/types.ts`

```typescript
// Shared types for API requests and responses
export interface Agent {
  id: string;
  name: string;
  type: string;
  status: string;
  capabilities: string[];
  created_at: string;
  updated_at: string;
}

export interface CreateAgentRequest {
  name: string;
  type: string;
  capabilities?: string[];
  config?: Record<string, any>;
}

export interface UpdateAgentRequest {
  name?: string;
  status?: string;
  capabilities?: string[];
  config?: Record<string, any>;
}

// Add more types as needed
```

## Testing Rules

### Test File Organization

```
backend/tests/                  # Backend tests
├── unit/                      # Unit tests
│   ├── test_agents.py
│   ├── test_tasks.py
│   └── test_llm_providers.py
├── integration/               # Integration tests
│   ├── test_agent_task_flow.py
│   └── test_api_endpoints.py
└── e2e/                       # End-to-end tests
    └── test_user_workflows.py

frontend/src/                   # Frontend tests
├── components/
│   ├── AgentList.tsx
│   └── AgentList.test.tsx     # Co-located with component
├── api/
│   ├── agents.ts
│   └── agents.test.ts         # Co-located with API module
└── utils/
    ├── helpers.ts
    └── helpers.test.ts        # Co-located with utilities
```

### Backend Testing Rules

#### Test File Naming

- Unit tests: `test_<module_name>.py`
- Integration tests: `test_<feature>_integration.py`
- E2E tests: `test_<workflow>_e2e.py`

#### Test Structure

```python
"""
Test module for agent functionality.

Tests cover:
- Agent creation and validation
- Agent lifecycle management
- Agent capability matching
"""

import pytest
from unittest.mock import Mock, patch
from agent_framework.base_agent import BaseAgent

class TestAgentCreation:
    """Test agent creation and initialization."""
    
    def test_create_agent_with_valid_data(self):
        """Test creating agent with valid configuration."""
        agent = BaseAgent(
            name="TestAgent",
            agent_type="worker",
            capabilities=["task_execution"]
        )
        
        assert agent.name == "TestAgent"
        assert agent.agent_type == "worker"
        assert "task_execution" in agent.capabilities
    
    def test_create_agent_with_invalid_type(self):
        """Test creating agent with invalid type raises error."""
        with pytest.raises(ValueError, match="Invalid agent type"):
            BaseAgent(
                name="TestAgent",
                agent_type="invalid_type",
                capabilities=[]
            )
    
    @pytest.mark.asyncio
    async def test_agent_initialization(self):
        """Test async agent initialization."""
        agent = BaseAgent(name="TestAgent", agent_type="worker")
        await agent.initialize()
        
        assert agent.status == "ready"
        assert agent.initialized is True


class TestAgentExecution:
    """Test agent task execution."""
    
    @pytest.fixture
    def mock_llm(self):
        """Fixture for mocked LLM provider."""
        return Mock()
    
    @pytest.mark.asyncio
    async def test_execute_task_success(self, mock_llm):
        """Test successful task execution."""
        agent = BaseAgent(name="TestAgent", agent_type="worker")
        agent.llm = mock_llm
        mock_llm.generate.return_value = "Task completed"
        
        result = await agent.execute_task("Test task")
        
        assert result.status == "completed"
        assert result.output == "Task completed"
        mock_llm.generate.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_execute_task_failure(self, mock_llm):
        """Test task execution failure handling."""
        agent = BaseAgent(name="TestAgent", agent_type="worker")
        agent.llm = mock_llm
        mock_llm.generate.side_effect = Exception("LLM error")
        
        result = await agent.execute_task("Test task")
        
        assert result.status == "failed"
        assert "LLM error" in result.error
```

#### Required Test Coverage

- **Minimum coverage**: 80% for all modules
- **Critical paths**: 100% coverage required
  - Authentication and authorization
  - Data validation
  - Error handling
  - Security-sensitive code

#### Running Backend Tests

```bash
cd backend

# Run all tests
pytest

# Run with coverage
pytest --cov=. --cov-report=html --cov-report=term

# Run specific test file
pytest tests/unit/test_agents.py

# Run specific test class
pytest tests/unit/test_agents.py::TestAgentCreation

# Run specific test
pytest tests/unit/test_agents.py::TestAgentCreation::test_create_agent_with_valid_data

# Run with verbose output
pytest -v

# Run only failed tests
pytest --lf

# Run tests matching pattern
pytest -k "agent"
```

### Frontend Testing Rules

#### Test File Naming

- Component tests: `<ComponentName>.test.tsx`
- API tests: `<module>.test.ts`
- Utility tests: `<utility>.test.ts`
- Hook tests: `use<HookName>.test.ts`

#### Component Testing

```typescript
// AgentList.test.tsx
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import AgentList from './AgentList';
import { agentApi } from '@/api/agents';

// Mock the API module
vi.mock('@/api/agents');

describe('AgentList', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders loading state initially', () => {
    render(<AgentList />);
    expect(screen.getByText(/loading/i)).toBeInTheDocument();
  });

  it('renders agents after loading', async () => {
    const mockAgents = [
      { id: '1', name: 'Agent 1', type: 'worker', status: 'active' },
      { id: '2', name: 'Agent 2', type: 'manager', status: 'idle' },
    ];
    
    vi.mocked(agentApi.getAll).mockResolvedValue(mockAgents);

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText('Agent 1')).toBeInTheDocument();
      expect(screen.getByText('Agent 2')).toBeInTheDocument();
    });
  });

  it('handles error state', async () => {
    vi.mocked(agentApi.getAll).mockRejectedValue(new Error('API Error'));

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText(/error/i)).toBeInTheDocument();
    });
  });

  it('deletes agent on button click', async () => {
    const mockAgents = [
      { id: '1', name: 'Agent 1', type: 'worker', status: 'active' },
    ];
    
    vi.mocked(agentApi.getAll).mockResolvedValue(mockAgents);
    vi.mocked(agentApi.delete).mockResolvedValue();

    render(<AgentList />);

    await waitFor(() => {
      expect(screen.getByText('Agent 1')).toBeInTheDocument();
    });

    const deleteButton = screen.getByRole('button', { name: /delete/i });
    await userEvent.click(deleteButton);

    await waitFor(() => {
      expect(agentApi.delete).toHaveBeenCalledWith('1');
    });
  });
});
```

#### API Module Testing

```typescript
// agents.test.ts
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { agentApi } from './agents';
import { apiClient } from './client';

// Mock the apiClient
vi.mock('./client');

describe('agentApi', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  describe('getAll', () => {
    it('fetches all agents', async () => {
      const mockAgents = [
        { id: '1', name: 'Agent 1' },
        { id: '2', name: 'Agent 2' },
      ];

      vi.mocked(apiClient.get).mockResolvedValue({ data: mockAgents });

      const result = await agentApi.getAll();

      expect(apiClient.get).toHaveBeenCalledWith('/agents');
      expect(result).toEqual(mockAgents);
    });

    it('throws error on failure', async () => {
      vi.mocked(apiClient.get).mockRejectedValue(new Error('Network error'));

      await expect(agentApi.getAll()).rejects.toThrow('Network error');
    });
  });

  describe('create', () => {
    it('creates new agent', async () => {
      const newAgent = { name: 'New Agent', type: 'worker' };
      const createdAgent = { id: '1', ...newAgent };

      vi.mocked(apiClient.post).mockResolvedValue({ data: createdAgent });

      const result = await agentApi.create(newAgent);

      expect(apiClient.post).toHaveBeenCalledWith('/agents', newAgent);
      expect(result).toEqual(createdAgent);
    });
  });

  describe('update', () => {
    it('updates existing agent', async () => {
      const updates = { name: 'Updated Name' };
      const updatedAgent = { id: '1', name: 'Updated Name', type: 'worker' };

      vi.mocked(apiClient.put).mockResolvedValue({ data: updatedAgent });

      const result = await agentApi.update('1', updates);

      expect(apiClient.put).toHaveBeenCalledWith('/agents/1', updates);
      expect(result).toEqual(updatedAgent);
    });
  });

  describe('delete', () => {
    it('deletes agent', async () => {
      vi.mocked(apiClient.delete).mockResolvedValue({ data: null });

      await agentApi.delete('1');

      expect(apiClient.delete).toHaveBeenCalledWith('/agents/1');
    });
  });
});
```

#### Running Frontend Tests

```bash
cd frontend

# Run all tests
npm test

# Run tests in watch mode
npm test -- --watch

# Run with coverage
npm test -- --coverage

# Run specific test file
npm test -- agents.test.ts

# Run tests matching pattern
npm test -- --grep "agent"

# Update snapshots
npm test -- -u
```

## Test-Driven Development (TDD) Workflow

### For New Features

1. **Write tests first** (Red phase)
   ```bash
   # Create test file
   touch backend/tests/unit/test_new_feature.py
   
   # Write failing tests
   # Run tests - they should fail
   pytest tests/unit/test_new_feature.py
   ```

2. **Implement feature** (Green phase)
   ```bash
   # Write minimal code to pass tests
   # Run tests - they should pass
   pytest tests/unit/test_new_feature.py
   ```

3. **Refactor** (Refactor phase)
   ```bash
   # Improve code quality
   # Run tests - they should still pass
   pytest tests/unit/test_new_feature.py
   ```

### For Bug Fixes

1. **Write test that reproduces bug**
   ```python
   def test_bug_reproduction():
       """Test that reproduces bug #123."""
       # This test should fail initially
       result = buggy_function(input_data)
       assert result == expected_output
   ```

2. **Fix the bug**
   ```python
   # Fix the implementation
   ```

3. **Verify test passes**
   ```bash
   pytest tests/unit/test_bug_fix.py
   ```

### For Feature Modifications

1. **Update existing tests**
   ```python
   # Modify tests to reflect new behavior
   def test_modified_feature():
       """Test updated feature behavior."""
       result = modified_function(new_input)
       assert result == new_expected_output
   ```

2. **Modify implementation**
   ```python
   # Update code to match new requirements
   ```

3. **Ensure all tests pass**
   ```bash
   pytest  # Run full test suite
   ```

## Mandatory Testing Checklist

Before committing ANY code, verify:

### Backend Checklist

- [ ] Unit tests written for all new functions/classes
- [ ] Integration tests for API endpoints
- [ ] Tests cover success cases
- [ ] Tests cover error cases
- [ ] Tests cover edge cases
- [ ] All tests pass locally
- [ ] Coverage meets minimum threshold (80%)
- [ ] No skipped tests without justification
- [ ] Mock external dependencies properly
- [ ] Tests are deterministic (no flaky tests)

### Frontend Checklist

- [ ] Component tests for all new components
- [ ] API module tests for all API functions
- [ ] Tests use apiClient (not raw fetch)
- [ ] Tests cover user interactions
- [ ] Tests cover loading states
- [ ] Tests cover error states
- [ ] All tests pass locally
- [ ] No console errors in tests
- [ ] Mocks are properly cleaned up
- [ ] Tests are isolated (no shared state)

## Common Testing Patterns

### Backend Patterns

#### Fixtures

```python
import pytest
from database.connection import get_db_session

@pytest.fixture
def db_session():
    """Provide database session for tests."""
    session = get_db_session()
    yield session
    session.rollback()
    session.close()

@pytest.fixture
def sample_agent():
    """Provide sample agent for tests."""
    return {
        "name": "TestAgent",
        "type": "worker",
        "capabilities": ["task_execution"]
    }
```

#### Mocking

```python
from unittest.mock import Mock, patch, MagicMock

# Mock function
@patch('module.function_name')
def test_with_mock(mock_function):
    mock_function.return_value = "mocked result"
    result = call_function_that_uses_mock()
    assert result == "expected"

# Mock class
@patch('module.ClassName')
def test_with_mock_class(MockClass):
    mock_instance = MockClass.return_value
    mock_instance.method.return_value = "mocked"
    # Test code

# Mock async function
@pytest.mark.asyncio
@patch('module.async_function')
async def test_async_mock(mock_async):
    mock_async.return_value = "mocked"
    result = await function_under_test()
    assert result == "expected"
```

#### Parametrized Tests

```python
@pytest.mark.parametrize("input,expected", [
    ("valid_input", "valid_output"),
    ("another_input", "another_output"),
    ("edge_case", "edge_result"),
])
def test_multiple_cases(input, expected):
    result = function_under_test(input)
    assert result == expected
```

### Frontend Patterns

#### Component Testing

```typescript
// Test rendering
it('renders correctly', () => {
  render(<Component />);
  expect(screen.getByText('Expected Text')).toBeInTheDocument();
});

// Test user interaction
it('handles click event', async () => {
  const handleClick = vi.fn();
  render(<Button onClick={handleClick} />);
  
  await userEvent.click(screen.getByRole('button'));
  
  expect(handleClick).toHaveBeenCalledTimes(1);
});

// Test async data loading
it('loads and displays data', async () => {
  vi.mocked(api.getData).mockResolvedValue(mockData);
  
  render(<DataComponent />);
  
  await waitFor(() => {
    expect(screen.getByText(mockData.title)).toBeInTheDocument();
  });
});
```

#### Custom Hooks Testing

```typescript
import { renderHook, waitFor } from '@testing-library/react';

it('fetches data on mount', async () => {
  vi.mocked(api.getData).mockResolvedValue(mockData);
  
  const { result } = renderHook(() => useData());
  
  await waitFor(() => {
    expect(result.current.data).toEqual(mockData);
    expect(result.current.loading).toBe(false);
  });
});
```

## Enforcement

### Pre-Commit Checks

```bash
# Backend
cd backend
pytest --cov=. --cov-fail-under=80

# Frontend
cd frontend
npm test -- --coverage --passWithNoTests=false
```

### Code Review Requirements

Reviewers must verify:

- [ ] All new code has corresponding tests
- [ ] Tests are meaningful (not just for coverage)
- [ ] API calls use apiClient (no raw fetch)
- [ ] Tests pass in CI/CD
- [ ] Coverage meets threshold
- [ ] No skipped or commented-out tests

### CI/CD Pipeline

Tests run automatically on:
- Every pull request
- Every push to main/develop
- Before deployment

**All tests must pass before merge.**

## Summary

### Golden Rules

1. 🚫 **Never use raw fetch()** - Always use apiClient
2. ✅ **Always write tests** - Tests are mandatory, not optional
3. 🔄 **Update tests with code** - Keep tests in sync
4. 📊 **Maintain coverage** - Minimum 80% coverage
5. 🧪 **Test before commit** - Run tests locally first

### Quick Reference

```bash
# Backend testing
cd backend
pytest --cov=. --cov-report=html

# Frontend testing
cd frontend
npm test -- --coverage

# Run before every commit
make pre-commit-check  # Backend
npm run pre-commit     # Frontend
```

**Remember**: Good tests are an investment in code quality, maintainability, and confidence. Write them diligently!
