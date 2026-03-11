import { describe, expect, it } from 'vitest';
import { shouldAttemptTokenRefresh } from '@/api/client';

describe('apiClient token refresh guard', () => {
  it('does not refresh tokens for authentication endpoints', () => {
    expect(shouldAttemptTokenRefresh('/auth/login')).toBe(false);
    expect(shouldAttemptTokenRefresh('/auth/logout')).toBe(false);
    expect(shouldAttemptTokenRefresh('/auth/refresh')).toBe(false);
    expect(shouldAttemptTokenRefresh('/auth/register')).toBe(false);
    expect(shouldAttemptTokenRefresh('/auth/setup/status')).toBe(false);
    expect(shouldAttemptTokenRefresh('/auth/setup/initialize')).toBe(false);
    expect(shouldAttemptTokenRefresh('http://localhost:8000/api/v1/auth/login')).toBe(false);
  });

  it('still allows refresh for protected business endpoints', () => {
    expect(shouldAttemptTokenRefresh('/users/me')).toBe(true);
    expect(shouldAttemptTokenRefresh('/missions/123')).toBe(true);
    expect(shouldAttemptTokenRefresh(undefined)).toBe(true);
  });
});
