import axios, { AxiosError } from 'axios';
import type { AxiosInstance, AxiosRequestConfig, AxiosResponse } from 'axios';
import { useAuthStore } from '../stores/authStore';
import toast from 'react-hot-toast';

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
          toast.error(errorData?.message || errorData?.detail || 'Invalid request. Please check your input.', {
            duration: 5000,
          });
          break;

        case 403:
          // Forbidden
          toast.error('You do not have permission to perform this action.', {
            duration: 4000,
          });
          break;

        case 404:
          // Not Found
          toast.error('The requested resource was not found.', {
            duration: 4000,
          });
          break;

        case 422:
          // Unprocessable Entity - Validation errors
          toast.error(errorData?.message || errorData?.detail || 'Request validation failed.', {
            duration: 5000,
          });
          break;

        case 500:
          // Internal Server Error
          toast.error('An unexpected error occurred. Please try again later.', {
            duration: 5000,
          });
          break;

        case 502:
          // Bad Gateway
          toast.error('The service is temporarily unavailable. Please try again later.', {
            duration: 5000,
          });
          break;

        case 503:
          // Service Unavailable
          toast.error('The service is under maintenance. Please try again later.', {
            duration: 5000,
          });
          break;

        default:
          // Catch-all for other HTTP errors (4xx, 5xx)
          if (status >= 400) {
            const message = errorData?.message || errorData?.detail || `Request failed with status ${status}`;
            toast.error(message, {
              duration: 5000,
            });
          }
          break;
      }
    } else if (error.message === 'Network Error') {
      // Handle network errors
      toast.error('Unable to connect to the server. Please check your connection.', {
        duration: 5000,
      });
    } else if (error.code === 'ECONNABORTED') {
      // Handle timeout
      toast.error('The request took too long to complete. Please try again.', {
        duration: 5000,
      });
    } else {
      // Catch-all for any other errors
      toast.error(error.message || 'An unexpected error occurred.', {
        duration: 4000,
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
