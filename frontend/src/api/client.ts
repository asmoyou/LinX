import axios, { AxiosError } from 'axios';
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import { useAuthStore } from '../stores/authStore';
import { useNotificationStore } from '../stores/notificationStore';

/**
 * API Client Configuration
 */
const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000/api/v1';
const API_TIMEOUT = 30000; // 30 seconds

/**
 * Request cancellation tokens
 */
const cancelTokens = new Map<string, AbortController>();

/**
 * Create axios instance with default configuration
 */
const apiClient: AxiosInstance = axios.create({
  baseURL: API_BASE_URL,
  timeout: API_TIMEOUT,
  headers: {
    'Content-Type': 'application/json',
  },
});

/**
 * Request interceptor
 * - Add authentication token
 * - Add request cancellation support
 * - Log requests in development
 */
apiClient.interceptors.request.use(
  (config) => {
    // Add auth token from store
    const token = useAuthStore.getState().token;
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }

    // Add cancellation token
    const controller = new AbortController();
    config.signal = controller.signal;
    
    // Store controller for potential cancellation
    if (config.url) {
      const key = `${config.method}-${config.url}`;
      cancelTokens.set(key, controller);
    }

    // Log in development
    if (import.meta.env.DEV) {
      console.log(`[API Request] ${config.method?.toUpperCase()} ${config.url}`, config.data);
    }

    return config;
  },
  (error) => {
    console.error('[API Request Error]', error);
    return Promise.reject(error);
  }
);

/**
 * Response interceptor
 * - Handle successful responses
 * - Handle errors globally
 * - Implement retry logic
 * - Handle token refresh
 */
apiClient.interceptors.response.use(
  (response: AxiosResponse) => {
    // Log in development
    if (import.meta.env.DEV) {
      console.log(`[API Response] ${response.config.method?.toUpperCase()} ${response.config.url}`, response.data);
    }

    // Remove cancellation token
    if (response.config.url) {
      const key = `${response.config.method}-${response.config.url}`;
      cancelTokens.delete(key);
    }

    return response;
  },
  async (error: AxiosError) => {
    const originalRequest = error.config as AxiosRequestConfig & { _retry?: boolean };

    // Log error in development
    if (import.meta.env.DEV) {
      console.error('[API Response Error]', error.response?.status, error.message);
    }

    // Handle 401 Unauthorized - Token expired
    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Try to refresh token
        const refreshToken = localStorage.getItem('refresh_token');
        if (refreshToken) {
          const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          });

          const { token } = response.data;
          useAuthStore.getState().setToken(token);

          // Retry original request with new token
          if (originalRequest.headers) {
            originalRequest.headers.Authorization = `Bearer ${token}`;
          }
          return apiClient(originalRequest);
        }
      } catch (refreshError) {
        // Refresh failed, logout user
        useAuthStore.getState().logout();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      }
    }

    // Handle specific error status codes
    if (error.response) {
      const status = error.response.status;
      const errorData = error.response.data as any;
      
      switch (status) {
        case 400:
          // Bad Request - Validation errors
          useNotificationStore.getState().addNotification({
            type: 'error',
            title: 'Validation Error',
            message: errorData?.message || errorData?.detail || 'Invalid request. Please check your input.',
          });
          break;

        case 403:
          // Forbidden
          useNotificationStore.getState().addNotification({
            type: 'error',
            title: 'Access Denied',
            message: 'You do not have permission to perform this action.',
          });
          break;

        case 404:
          // Not Found
          useNotificationStore.getState().addNotification({
            type: 'error',
            title: 'Not Found',
            message: 'The requested resource was not found.',
          });
          break;

        case 422:
          // Unprocessable Entity - Validation errors
          useNotificationStore.getState().addNotification({
            type: 'error',
            title: 'Validation Error',
            message: errorData?.message || errorData?.detail || 'Request validation failed.',
          });
          break;

        case 500:
          // Internal Server Error
          useNotificationStore.getState().addNotification({
            type: 'error',
            title: 'Server Error',
            message: 'An unexpected error occurred. Please try again later.',
          });
          break;

        case 502:
          // Bad Gateway
          useNotificationStore.getState().addNotification({
            type: 'error',
            title: 'Service Unavailable',
            message: 'The service is temporarily unavailable. Please try again later.',
          });
          break;

        case 503:
          // Service Unavailable
          useNotificationStore.getState().addNotification({
            type: 'error',
            title: 'Service Unavailable',
            message: 'The service is under maintenance. Please try again later.',
          });
          break;

        default:
          // Catch-all for other HTTP errors (4xx, 5xx)
          if (status >= 400) {
            const message = errorData?.message || errorData?.detail || `Request failed with status ${status}`;
            useNotificationStore.getState().addNotification({
              type: 'error',
              title: status >= 500 ? 'Server Error' : 'Request Failed',
              message: message,
            });
          }
          break;
      }
    } else if (error.message === 'Network Error') {
      // Handle network errors
      useNotificationStore.getState().addNotification({
        type: 'error',
        title: 'Network Error',
        message: 'Unable to connect to the server. Please check your connection.',
      });
    } else if (error.code === 'ECONNABORTED') {
      // Handle timeout
      useNotificationStore.getState().addNotification({
        type: 'error',
        title: 'Request Timeout',
        message: 'The request took too long to complete. Please try again.',
      });
    } else {
      // Catch-all for any other errors
      useNotificationStore.getState().addNotification({
        type: 'error',
        title: 'Error',
        message: error.message || 'An unexpected error occurred.',
      });
    }

    return Promise.reject(error);
  }
);

/**
 * Cancel all pending requests
 */
export const cancelAllRequests = () => {
  cancelTokens.forEach((controller) => {
    controller.abort();
  });
  cancelTokens.clear();
};

/**
 * Cancel specific request
 */
export const cancelRequest = (method: string, url: string) => {
  const key = `${method}-${url}`;
  const controller = cancelTokens.get(key);
  if (controller) {
    controller.abort();
    cancelTokens.delete(key);
  }
};

/**
 * Retry failed request
 */
export const retryRequest = async <T>(
  requestFn: () => Promise<T>,
  maxRetries = 3,
  delay = 1000
): Promise<T> => {
  let lastError: Error;

  for (let i = 0; i < maxRetries; i++) {
    try {
      return await requestFn();
    } catch (error) {
      lastError = error as Error;
      if (i < maxRetries - 1) {
        await new Promise((resolve) => setTimeout(resolve, delay * (i + 1)));
      }
    }
  }

  throw lastError!;
};

export default apiClient;
