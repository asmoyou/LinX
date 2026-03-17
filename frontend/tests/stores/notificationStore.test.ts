import { beforeEach, describe, expect, it, vi } from 'vitest';
import { clearClientSession } from '@/utils/clientSession';
import { useAuthStore } from '@/stores/authStore';
import { useNotificationStore } from '@/stores/notificationStore';

vi.mock('react-hot-toast', () => ({
  default: {
    success: vi.fn(),
  },
}));

describe('notificationStore session reset', () => {
  beforeEach(() => {
    localStorage.clear();
    useAuthStore.setState({
      user: null,
      token: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    });
    useNotificationStore.getState().reset();
  });

  it('clears persisted notifications when the client session is cleared', () => {
    useAuthStore.setState({
      user: {
        id: 'user-1',
        username: 'alice',
        email: 'alice@example.com',
        role: 'user',
      },
      token: 'access-token',
      isAuthenticated: true,
      isLoading: false,
      error: null,
    });

    useNotificationStore.getState().addNotification({
      type: 'success',
      title: 'Logged out',
      message: 'You have been logged out successfully',
    });

    expect(useNotificationStore.getState().notifications).toHaveLength(1);

    clearClientSession();

    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(useNotificationStore.getState().notifications).toEqual([]);
    expect(useNotificationStore.getState().unreadCount).toBe(0);
  });
});
