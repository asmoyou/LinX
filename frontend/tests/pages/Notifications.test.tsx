import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { Notifications } from '@/pages/Notifications';
import { useNotificationStore } from '@/stores/notificationStore';
import { notificationsApi } from '@/api/notifications';

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    i18n: { language: 'en' },
    t: (key: string, fallbackOrOptions?: string | Record<string, unknown>, maybeOptions?: Record<string, unknown>) => {
      const template =
        typeof fallbackOrOptions === 'string'
          ? fallbackOrOptions
          : key;
      const options =
        typeof fallbackOrOptions === 'object' && fallbackOrOptions !== null
          ? fallbackOrOptions
          : maybeOptions ?? {};

      return template.replace(/\{\{(\w+)\}\}/g, (_, token: string) => {
        const value = options[token];
        return value === undefined || value === null ? '' : String(value);
      });
    },
  }),
}));

vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
}));

vi.mock('@/api/notifications', () => ({
  notificationsApi: {
    getAll: vi.fn(),
    markAsRead: vi.fn(),
    markAllAsRead: vi.fn(),
    deleteOne: vi.fn(),
    clear: vi.fn(),
  },
}));

vi.mock('react-hot-toast', () => ({
  default: Object.assign(vi.fn(), {
    success: vi.fn(),
  }),
}));

describe('Notifications page local fallback mode', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    localStorage.clear();
    useNotificationStore.getState().reset();
    vi.mocked(notificationsApi.getAll).mockResolvedValue({
      items: [],
      total: 0,
      unread_count: 0,
    });
    vi.stubGlobal('confirm', vi.fn(() => true));
  });

  it('shows toolbar actions for local notifications and applies them locally', async () => {
    useNotificationStore.getState().addNotification({
      type: 'info',
      title: 'Logged out',
      message: 'You have been logged out successfully',
    });

    render(<Notifications />);

    expect(await screen.findByText('Showing local history records')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Mark All Read' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear Read' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Clear All' })).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Mark All Read' }));

    await waitFor(() => {
      expect(useNotificationStore.getState().notifications[0]?.read).toBe(true);
    });

    fireEvent.click(screen.getByRole('button', { name: 'Clear Read' }));

    await waitFor(() => {
      expect(useNotificationStore.getState().notifications).toEqual([]);
    });
  });
});
