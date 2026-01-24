# Frontend Integration Guide

前端与后端 API 集成的最佳实践和配置建议。

## HTTP 请求配置

### 超时设置

**重要**：所有 API 请求都应该设置合理的超时时间，避免长时间等待。

```typescript
// 推荐的超时配置
const API_TIMEOUTS = {
  // 快速查询（列表、状态检查）
  FAST: 5000,        // 5秒
  
  // 普通操作（CRUD）
  NORMAL: 15000,     // 15秒
  
  // 耗时操作（测试连接、生成内容）
  SLOW: 30000,       // 30秒
  
  // 长时间操作（文件上传、批量处理）
  LONG: 60000,       // 60秒
};

// 使用 fetch 设置超时
const fetchWithTimeout = async (url: string, options: RequestInit = {}, timeout: number = API_TIMEOUTS.NORMAL) => {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), timeout);
  
  try {
    const response = await fetch(url, {
      ...options,
      signal: controller.signal,
    });
    clearTimeout(timeoutId);
    return response;
  } catch (error) {
    clearTimeout(timeoutId);
    if (error.name === 'AbortError') {
      throw new Error(`Request timeout after ${timeout}ms`);
    }
    throw error;
  }
};

// 使用 axios 设置超时
import axios from 'axios';

const apiClient = axios.create({
  baseURL: '/api/v1',
  timeout: API_TIMEOUTS.NORMAL,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 为特定请求设置不同超时
apiClient.get('/llm/providers/available', {
  timeout: API_TIMEOUTS.FAST,  // 快速查询
});

apiClient.post('/agents/test', data, {
  timeout: API_TIMEOUTS.SLOW,  // 耗时操作
});
```

### 错误处理

```typescript
// 统一的错误处理
const handleApiError = (error: any) => {
  if (error.name === 'AbortError' || error.message.includes('timeout')) {
    return {
      type: 'timeout',
      message: '请求超时，请检查网络连接或稍后重试',
    };
  }
  
  if (error.response) {
    // 服务器返回错误
    const status = error.response.status;
    const data = error.response.data;
    
    switch (status) {
      case 401:
        return { type: 'auth', message: '未登录或登录已过期' };
      case 403:
        return { type: 'permission', message: '没有权限执行此操作' };
      case 404:
        return { type: 'notfound', message: '请求的资源不存在' };
      case 500:
        return { type: 'server', message: data.detail || '服务器错误' };
      default:
        return { type: 'unknown', message: data.detail || '请求失败' };
    }
  }
  
  if (error.request) {
    // 请求发送但没有响应
    return {
      type: 'network',
      message: '网络连接失败，请检查网络设置',
    };
  }
  
  // 其他错误
  return {
    type: 'unknown',
    message: error.message || '未知错误',
  };
};

// 使用示例
try {
  const response = await fetchWithTimeout('/api/v1/agents', {}, API_TIMEOUTS.FAST);
  const data = await response.json();
  return data;
} catch (error) {
  const errorInfo = handleApiError(error);
  console.error('API Error:', errorInfo);
  // 显示用户友好的错误消息
  showErrorToast(errorInfo.message);
  throw errorInfo;
}
```

## API 端点超时建议

| 端点 | 推荐超时 | 说明 |
|------|---------|------|
| `GET /llm/providers/available` | 5秒 | 快速查询，从配置读取 |
| `GET /llm/providers` | 5秒 | 快速查询，不进行健康检查 |
| `GET /agents` | 5秒 | 列表查询 |
| `POST /agents` | 15秒 | 创建操作 |
| `PUT /agents/{id}` | 15秒 | 更新操作 |
| `POST /agents/{id}/test` | 30秒 | LLM 生成，可能较慢 |
| `POST /llm/providers/test-connection` | 30秒 | 网络连接测试 |
| `POST /knowledge/upload` | 60秒 | 文件上传 |

## 重试策略

对于可能失败的请求，实现重试机制：

```typescript
const retryRequest = async <T>(
  requestFn: () => Promise<T>,
  maxRetries: number = 3,
  delayMs: number = 1000,
): Promise<T> => {
  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn();
    } catch (error) {
      const errorInfo = handleApiError(error);
      
      // 不重试的错误类型
      if (['auth', 'permission', 'notfound'].includes(errorInfo.type)) {
        throw error;
      }
      
      // 最后一次尝试失败
      if (i === maxRetries - 1) {
        throw error;
      }
      
      // 等待后重试
      await new Promise(resolve => setTimeout(resolve, delayMs * (i + 1)));
      console.log(`Retrying request (${i + 1}/${maxRetries})...`);
    }
  }
  
  throw new Error('Max retries exceeded');
};

// 使用示例
const fetchProviders = () => 
  fetchWithTimeout('/api/v1/llm/providers/available', {}, API_TIMEOUTS.FAST);

const providers = await retryRequest(fetchProviders, 3, 1000);
```

## Loading 状态管理

```typescript
// React 示例
const [loading, setLoading] = useState(false);
const [error, setError] = useState<string | null>(null);

const fetchData = async () => {
  setLoading(true);
  setError(null);
  
  try {
    const response = await fetchWithTimeout(
      '/api/v1/agents',
      {},
      API_TIMEOUTS.FAST
    );
    const data = await response.json();
    setData(data);
  } catch (err) {
    const errorInfo = handleApiError(err);
    setError(errorInfo.message);
  } finally {
    setLoading(false);
  }
};

// UI 显示
{loading && <Spinner />}
{error && <ErrorAlert message={error} />}
{!loading && !error && <DataDisplay data={data} />}
```

## 请求取消

用户导航离开页面时取消正在进行的请求：

```typescript
// React useEffect 示例
useEffect(() => {
  const controller = new AbortController();
  
  const fetchData = async () => {
    try {
      const response = await fetch('/api/v1/agents', {
        signal: controller.signal,
      });
      const data = await response.json();
      setData(data);
    } catch (error) {
      if (error.name !== 'AbortError') {
        console.error('Fetch error:', error);
      }
    }
  };
  
  fetchData();
  
  // 清理：组件卸载时取消请求
  return () => controller.abort();
}, []);
```

## 认证 Token 管理

```typescript
// Token 存储
const setAuthToken = (token: string) => {
  localStorage.setItem('auth_token', token);
  apiClient.defaults.headers.common['Authorization'] = `Bearer ${token}`;
};

const getAuthToken = (): string | null => {
  return localStorage.setItem('auth_token');
};

const clearAuthToken = () => {
  localStorage.removeItem('auth_token');
  delete apiClient.defaults.headers.common['Authorization'];
};

// 请求拦截器：自动添加 token
apiClient.interceptors.request.use(
  (config) => {
    const token = getAuthToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器：处理 401
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearAuthToken();
      // 重定向到登录页
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

## 性能优化

### 请求去重

避免重复请求：

```typescript
const pendingRequests = new Map<string, Promise<any>>();

const fetchWithDedup = async (url: string, options: RequestInit = {}) => {
  const key = `${url}-${JSON.stringify(options)}`;
  
  if (pendingRequests.has(key)) {
    return pendingRequests.get(key);
  }
  
  const promise = fetchWithTimeout(url, options)
    .finally(() => pendingRequests.delete(key));
  
  pendingRequests.set(key, promise);
  return promise;
};
```

### 请求缓存

缓存不常变化的数据：

```typescript
const cache = new Map<string, { data: any; timestamp: number }>();
const CACHE_TTL = 5 * 60 * 1000; // 5分钟

const fetchWithCache = async (url: string, options: RequestInit = {}) => {
  const cached = cache.get(url);
  
  if (cached && Date.now() - cached.timestamp < CACHE_TTL) {
    return cached.data;
  }
  
  const response = await fetchWithTimeout(url, options);
  const data = await response.json();
  
  cache.set(url, { data, timestamp: Date.now() });
  return data;
};

// 使用示例：缓存 providers 列表
const providers = await fetchWithCache('/api/v1/llm/providers/available');
```

## 总结

**关键原则**：

1. ✅ **总是设置超时** - 不要依赖浏览器默认超时
2. ✅ **快速失败** - 5-30秒内返回错误，不要让用户等待太久
3. ✅ **友好的错误消息** - 告诉用户发生了什么，如何解决
4. ✅ **适当的重试** - 网络错误可以重试，认证错误不要重试
5. ✅ **取消无用请求** - 用户离开页面时取消请求
6. ✅ **缓存合理数据** - 减少不必要的请求

**超时时间选择**：
- 快速查询：5秒
- 普通操作：15秒
- 耗时操作：30秒
- 长时间操作：60秒

**错误处理**：
- 超时：提示网络问题
- 401：重定向登录
- 403：提示权限不足
- 404：提示资源不存在
- 500：提示服务器错误

遵循这些原则，可以提供更好的用户体验，避免长时间等待和不明确的错误状态。
