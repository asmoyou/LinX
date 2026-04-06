import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
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
  afterEach(() => {
    vi.unstubAllGlobals();
  });

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

    await waitFor(() => {
      expect(vi.mocked(notificationsApi.getAll)).toHaveBeenCalled();
      expect(useNotificationStore.getState().notifications.length).toBeGreaterThan(0);
    });

    expect(
      await screen.findByText('These actions apply to local browser notifications.', {}, { timeout: 10000 })
    ).toBeInTheDocument();

    let markAllReadButton = await screen.findByRole('button', { name: 'Mark All Read' }, { timeout: 10000 });
    let clearReadButton = await screen.findByRole('button', { name: 'Clear Read' }, { timeout: 10000 });
    const clearAllButton = await screen.findByRole('button', { name: 'Clear All' }, { timeout: 10000 });

    expect(markAllReadButton).toBeInTheDocument();
    expect(clearReadButton).toBeInTheDocument();
    expect(clearAllButton).toBeInTheDocument();

    fireEvent.click(markAllReadButton);

    await waitFor(() => {
      expect(useNotificationStore.getState().notifications[0]?.read).toBe(true);
    });

    clearReadButton = await screen.findByRole('button', { name: 'Clear Read' }, { timeout: 10000 });
    fireEvent.click(clearReadButton);

    await waitFor(() => {
      expect(useNotificationStore.getState().notifications).toEqual([]);
    });
  });
});
