# Testing LLM Provider Connection Error Handling

This document describes how to test the LLM provider connection error handling to ensure proper error messages are displayed when providers are offline or unreachable.

## Overview

The LLM provider test connection feature should gracefully handle connection failures and display user-friendly error messages instead of generic 500 errors or JSON parsing errors.

## Test Scenarios

### 1. Provider Offline (Connection Refused)

**Setup:**
- Stop the Ollama service or use an invalid base URL
- Example: `http://localhost:11434` (when Ollama is not running)

**Expected Behavior:**
- Backend returns `TestConnectionResponse` with `success=False`
- Frontend displays specific error: "Failed to connect to Ollama: Connection refused"
- No 500 error or JSON parsing error

**Test Steps:**
1. Open Settings page
2. Click "Add Provider"
3. Fill in:
   - Name: `test-ollama`
   - Protocol: `Ollama`
   - Base URL: `http://localhost:11434`
4. Click "Test Connection"
5. Verify error message is clear and specific

### 2. Invalid URL Format

**Setup:**
- Use an invalid URL format
- Example: `not-a-valid-url`

**Expected Behavior:**
- Frontend validation catches the error before sending request
- Error message: "Base URL must start with http:// or https://"

**Test Steps:**
1. Open Settings page
2. Click "Add Provider"
3. Fill in invalid base URL
4. Verify validation error appears

### 3. Network Timeout

**Setup:**
- Use a URL that times out
- Example: `http://192.0.2.1:11434` (non-routable IP)

**Expected Behavior:**
- Backend times out after configured timeout (default 30s)
- Frontend displays: "Connection test failed: Request timeout"

**Test Steps:**
1. Open Settings page
2. Click "Add Provider"
3. Fill in non-routable URL
4. Set timeout to 5 seconds
5. Click "Test Connection"
6. Wait for timeout
7. Verify timeout error message

### 4. API Key Required (OpenAI Compatible)

**Setup:**
- Use OpenAI Compatible protocol without API key
- Example: `https://api.openai.com/v1`

**Expected Behavior:**
- Frontend validation requires API key for new providers
- For existing providers, stored API key is used if not provided

**Test Steps:**
1. Open Settings page
2. Click "Add Provider"
3. Select "OpenAI Compatible" protocol
4. Fill in base URL without API key
5. Click "Test Connection"
6. Verify error: "API key is required"

### 5. Invalid API Key

**Setup:**
- Use OpenAI Compatible protocol with invalid API key
- Example: `https://api.openai.com/v1` with key `invalid-key`

**Expected Behavior:**
- Backend receives 401 or 403 from provider
- Frontend displays: "Connection test failed: HTTP 401: Unauthorized"

**Test Steps:**
1. Open Settings page
2. Click "Add Provider"
3. Select "OpenAI Compatible" protocol
4. Fill in valid base URL with invalid API key
5. Click "Test Connection"
6. Verify authentication error message

## Implementation Details

### Backend Error Handling

The `test_connection` endpoint in `backend/api_gateway/routers/llm.py`:

```python
@router.post("/providers/test-connection", response_model=TestConnectionResponse)
async def test_connection(request: TestConnectionRequest):
    try:
        # ... connection logic ...
        return TestConnectionResponse(
            success=True,
            message="Successfully connected",
            available_models=models,
        )
    except Exception as e:
        # Always return TestConnectionResponse, never raise HTTPException
        return TestConnectionResponse(
            success=False,
            message="Connection test failed",
            error=str(e),
            available_models=[],
        )
```

**Key Points:**
- Always returns `TestConnectionResponse` (never raises HTTPException)
- Captures all exceptions and returns them in the `error` field
- Updates provider test status in database

### Frontend Error Handling

The frontend uses `apiClient` which has global error interceptors:

```typescript
// frontend/src/api/client.ts
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    // Handle 500 errors globally
    if (error.response?.status === 500) {
      useNotificationStore.getState().addNotification({
        type: 'error',
        title: 'Server Error',
        message: 'An unexpected error occurred.',
      });
    }
    return Promise.reject(error);
  }
);
```

**Key Points:**
- Global error handling for all HTTP status codes
- Automatic token refresh on 401
- Consistent error message format

### Component Error Handling

The `AddProviderModal` component:

```typescript
const testConnection = async () => {
  try {
    const data = await llmApi.testConnection({
      protocol,
      base_url,
      api_key,
      timeout,
    });

    if (data.success) {
      // Show success message
      toast.success(`Connected! Found ${data.available_models.length} models`);
    } else {
      // Show specific error from backend
      toast.error(`Connection failed: ${data.error || data.message}`);
    }
  } catch (error) {
    // Handle network errors or unexpected errors
    toast.error(`Test failed: ${error.message}`);
  }
};
```

**Key Points:**
- Uses `llmApi` wrapper (not raw fetch)
- Checks `success` field in response
- Displays specific error messages from backend
- Handles network errors separately

## Debugging

### Backend Logs

Check backend logs for detailed error information:

```bash
cd backend
tail -f backend.log | grep "test_connection"
```

Look for:
- `✓ Connection test successful: X models found`
- `✗ Connection test failed: <error message>`
- `✗ Test connection error: <error message>`

### Frontend Console

Open browser DevTools console and look for:
- `[API Request] POST /llm/providers/test-connection`
- `[API Response] POST /llm/providers/test-connection`
- `[API Response Error] 500 <error message>`

### Network Tab

Check the Network tab in DevTools:
- Request payload should contain `protocol`, `base_url`, `api_key`, `timeout`
- Response should always be JSON with `success`, `message`, `error`, `available_models`
- Status code should be 200 (even for connection failures)

## Common Issues

### Issue: "JSON parsing error"

**Cause:** Frontend is using raw `fetch` instead of `apiClient`

**Solution:** Ensure all API calls use the `llmApi` wrapper from `frontend/src/api/llm.ts`

### Issue: "500 Internal Server Error" displayed to user

**Cause:** Backend is raising HTTPException instead of returning TestConnectionResponse

**Solution:** Ensure `test_connection` endpoint catches all exceptions and returns TestConnectionResponse

### Issue: Generic error message instead of specific error

**Cause:** Error message not being passed from backend to frontend

**Solution:** Check that backend includes error details in `TestConnectionResponse.error` field

## References

- Backend: `backend/api_gateway/routers/llm.py`
- Frontend API: `frontend/src/api/llm.ts`
- Frontend Component: `frontend/src/components/AddProviderModal.tsx`
- API Client: `frontend/src/api/client.ts`
