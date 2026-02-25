import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  AlertTriangle,
  Bell,
  CheckCheck,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ExternalLink,
  Info,
  RefreshCw,
  Search,
  Trash2,
  XCircle,
} from 'lucide-react';
import { notificationsApi } from '@/api/notifications';
import { GlassPanel } from '@/components/GlassPanel';
import {
  useNotificationStore,
  type Notification as LocalNotification,
} from '@/stores/notificationStore';
import type { NotificationSeverity, ServerNotification } from '@/types/notification';

type StatusFilter = 'all' | 'unread';

const PAGE_SIZE_OPTIONS = [20, 50, 100] as const;

const severityStyleMap: Record<
  NotificationSeverity,
  {
    icon: typeof Info;
    textClass: string;
    badgeClass: string;
    labelKey: string;
    fallback: string;
  }
> = {
  info: {
    icon: Info,
    textClass: 'text-blue-600 dark:text-blue-400',
    badgeClass: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    labelKey: 'notificationsPage.severity.info',
    fallback: 'Info',
  },
  success: {
    icon: CheckCircle2,
    textClass: 'text-emerald-600 dark:text-emerald-400',
    badgeClass: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    labelKey: 'notificationsPage.severity.success',
    fallback: 'Success',
  },
  warning: {
    icon: AlertTriangle,
    textClass: 'text-amber-600 dark:text-amber-400',
    badgeClass: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    labelKey: 'notificationsPage.severity.warning',
    fallback: 'Warning',
  },
  error: {
    icon: XCircle,
    textClass: 'text-red-600 dark:text-red-400',
    badgeClass: 'bg-red-100 text-red-700 dark:bg-red-900/30 dark:text-red-300',
    labelKey: 'notificationsPage.severity.error',
    fallback: 'Error',
  },
};

export const Notifications = () => {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();
  const {
    addNotification,
    replaceServerNotifications,
    notifications: storedNotifications,
    markAsRead: markLocalAsRead,
    removeNotification: removeLocalNotification,
  } = useNotificationStore();

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [severityFilter, setSeverityFilter] = useState<NotificationSeverity | 'all'>('all');
  const [searchInput, setSearchInput] = useState('');
  const [searchQuery, setSearchQuery] = useState('');

  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState<number>(20);

  const [isLoading, setIsLoading] = useState(true);
  const [isMutating, setIsMutating] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const [notifications, setNotifications] = useState<ServerNotification[]>([]);
  const [total, setTotal] = useState(0);
  const [unreadCount, setUnreadCount] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [pendingIds, setPendingIds] = useState<Set<string>>(new Set());

  const localFilteredNotifications = useMemo(() => {
    const keyword = searchQuery.trim().toLowerCase();

    return storedNotifications
      .filter((notification) => notification.source !== 'server')
      .filter((notification) => {
        if (statusFilter === 'unread' && notification.read) {
          return false;
        }

        if (severityFilter !== 'all' && notification.type !== severityFilter) {
          return false;
        }

        if (keyword) {
          const title = notification.title?.toLowerCase() || '';
          const message = notification.message?.toLowerCase() || '';
          if (!title.includes(keyword) && !message.includes(keyword)) {
            return false;
          }
        }

        return true;
      })
      .slice()
      .sort((left, right) => {
        const leftTs = new Date(left.timestamp).getTime();
        const rightTs = new Date(right.timestamp).getTime();
        return rightTs - leftTs;
      });
  }, [searchQuery, severityFilter, statusFilter, storedNotifications]);

  const isLocalFallbackMode =
    !isLoading && !errorMessage && total === 0 && localFilteredNotifications.length > 0;

  const effectiveTotal = isLocalFallbackMode ? localFilteredNotifications.length : total;
  const effectiveUnreadCount = isLocalFallbackMode
    ? localFilteredNotifications.filter((item) => !item.read).length
    : unreadCount;
  const totalPages = Math.max(1, Math.ceil(effectiveTotal / pageSize));
  const startIndex = effectiveTotal === 0 ? 0 : (page - 1) * pageSize + 1;
  const endIndex = Math.min(effectiveTotal, page * pageSize);

  const pageRangeLabel =
    effectiveTotal === 0
      ? t('notificationsPage.metrics.emptyRange', '0 / 0')
      : `${startIndex}-${endIndex}`;

  const paginationSummaryLabel =
    effectiveTotal === 0
      ? t('notificationsPage.paginationSummaryEmpty', '0 / 0')
      : t('notificationsPage.paginationSummary', '{{start}}-{{end}} / {{total}}', {
          start: startIndex,
          end: endIndex,
          total: effectiveTotal,
        });

  const localPageNotifications = useMemo(
    () =>
      isLocalFallbackMode
        ? localFilteredNotifications.slice((page - 1) * pageSize, page * pageSize)
        : [],
    [isLocalFallbackMode, localFilteredNotifications, page, pageSize]
  );

  const allOnPageSelected =
    !isLocalFallbackMode &&
    notifications.length > 0 &&
    notifications.every((item) => selectedIds.has(item.notification_id));

  const selectedRows = useMemo(
    () =>
      isLocalFallbackMode
        ? []
        : notifications.filter((item) => selectedIds.has(item.notification_id)),
    [isLocalFallbackMode, notifications, selectedIds]
  );

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setSearchQuery(searchInput.trim());
    }, 300);
    return () => window.clearTimeout(timer);
  }, [searchInput]);

  useEffect(() => {
    setPage(1);
  }, [statusFilter, severityFilter, searchQuery, pageSize]);

  useEffect(() => {
    setSelectedIds((prev) => {
      const next = new Set<string>();
      notifications.forEach((item) => {
        if (prev.has(item.notification_id)) next.add(item.notification_id);
      });
      return next;
    });
  }, [notifications]);

  useEffect(() => {
    if (page > totalPages) {
      setPage(totalPages);
    }
  }, [page, totalPages]);

  useEffect(() => {
    if (isLocalFallbackMode && selectedIds.size > 0) {
      setSelectedIds(new Set());
    }
  }, [isLocalFallbackMode, selectedIds.size]);

  const syncHeaderNotificationSnapshot = useCallback(async () => {
    const snapshot = await notificationsApi.getAll({
      status: 'all',
      limit: 100,
      offset: 0,
    });
    replaceServerNotifications(snapshot.items);
  }, [replaceServerNotifications]);

  const loadNotifications = useCallback(
    async (silent = false) => {
      if (!silent) setIsLoading(true);
      setErrorMessage(null);

      try {
        const response = await notificationsApi.getAll({
          status: statusFilter,
          severity: severityFilter === 'all' ? undefined : severityFilter,
          query: searchQuery || undefined,
          limit: pageSize,
          offset: (page - 1) * pageSize,
        });
        setNotifications(response.items);
        setTotal(response.total);
        setUnreadCount(response.unread_count);
      } catch (error: any) {
        setErrorMessage(
          error?.response?.data?.detail ||
            error?.message ||
            t('notificationsPage.loadFailed', 'Failed to load notifications')
        );
      } finally {
        if (!silent) setIsLoading(false);
      }
    },
    [page, pageSize, searchQuery, severityFilter, statusFilter, t]
  );

  useEffect(() => {
    void loadNotifications();
  }, [loadNotifications]);

  const withRowPending = async (notificationId: string, callback: () => Promise<void>) => {
    setPendingIds((prev) => new Set(prev).add(notificationId));
    try {
      await callback();
    } finally {
      setPendingIds((prev) => {
        const next = new Set(prev);
        next.delete(notificationId);
        return next;
      });
    }
  };

  const refreshData = async () => {
    await Promise.all([loadNotifications(true), syncHeaderNotificationSnapshot()]);
  };

  const handleMarkRead = async (notification: ServerNotification) => {
    if (notification.is_read) return;

    await withRowPending(notification.notification_id, async () => {
      await notificationsApi.markAsRead(notification.notification_id);
      addNotification({
        type: 'success',
        title: t('notificationsPage.markReadSuccessTitle', 'Marked as Read'),
        message: t('notificationsPage.markReadSuccessMessage', 'Notification marked as read'),
      });
      await refreshData();
    });
  };

  const handleDeleteOne = async (notification: ServerNotification) => {
    if (!confirm(t('notificationsPage.confirmDeleteOne', 'Delete this notification?'))) {
      return;
    }

    await withRowPending(notification.notification_id, async () => {
      await notificationsApi.deleteOne(notification.notification_id);
      addNotification({
        type: 'success',
        title: t('notificationsPage.deleteSuccessTitle', 'Deleted'),
        message: t('notificationsPage.deleteSuccessMessage', 'Notification deleted'),
      });
      await refreshData();
    });
  };

  const handleOpenAction = async (notification: ServerNotification) => {
    if (!notification.action_url) return;

    if (!notification.is_read) {
      await withRowPending(notification.notification_id, async () => {
        await notificationsApi.markAsRead(notification.notification_id);
      });
    }

    await refreshData();

    if (/^https?:\/\//.test(notification.action_url)) {
      window.open(notification.action_url, '_blank', 'noopener,noreferrer');
      return;
    }
    navigate(notification.action_url);
  };

  const handleMarkAllRead = async () => {
    setIsMutating(true);
    try {
      const result = await notificationsApi.markAllAsRead();
      addNotification({
        type: 'success',
        title: t('notificationsPage.markAllReadTitle', 'Marked All as Read'),
        message: t(
          'notificationsPage.markAllReadMessage',
          '{{count}} notifications updated',
          { count: result.updated }
        ),
      });
      await refreshData();
      setSelectedIds(new Set());
    } finally {
      setIsMutating(false);
    }
  };

  const handleClear = async (scope: 'read' | 'all') => {
    const confirmKey =
      scope === 'all'
        ? 'notificationsPage.confirmClearAll'
        : 'notificationsPage.confirmClearRead';

    if (
      !confirm(
        t(
          confirmKey,
          scope === 'all'
            ? 'Clear all notifications? This action cannot be undone.'
            : 'Clear all read notifications?'
        )
      )
    ) {
      return;
    }

    setIsMutating(true);
    try {
      const result = await notificationsApi.clear(scope);
      addNotification({
        type: 'success',
        title: t('notificationsPage.clearSuccessTitle', 'Notifications Cleared'),
        message: t(
          'notificationsPage.clearSuccessMessage',
          '{{count}} notifications removed',
          { count: result.deleted }
        ),
      });
      await refreshData();
      setSelectedIds(new Set());
    } finally {
      setIsMutating(false);
    }
  };

  const handleBulkMarkRead = async () => {
    const unreadIds = selectedRows
      .filter((item) => !item.is_read)
      .map((item) => item.notification_id);

    if (unreadIds.length === 0) {
      addNotification({
        type: 'info',
        title: t('notificationsPage.noUnreadSelectedTitle', 'No Unread Selected'),
        message: t('notificationsPage.noUnreadSelectedMessage', 'Selected notifications are already read'),
      });
      return;
    }

    setIsMutating(true);
    try {
      await Promise.all(unreadIds.map((id) => notificationsApi.markAsRead(id)));
      addNotification({
        type: 'success',
        title: t('notificationsPage.bulkMarkReadTitle', 'Batch Update Complete'),
        message: t(
          'notificationsPage.bulkMarkReadMessage',
          '{{count}} notifications marked as read',
          { count: unreadIds.length }
        ),
      });
      setSelectedIds(new Set());
      await refreshData();
    } finally {
      setIsMutating(false);
    }
  };

  const handleBulkDelete = async () => {
    if (selectedRows.length === 0) return;
    if (
      !confirm(
        t(
          'notificationsPage.confirmBulkDelete',
          'Delete {{count}} selected notifications?',
          { count: selectedRows.length }
        )
      )
    ) {
      return;
    }

    setIsMutating(true);
    try {
      await Promise.all(selectedRows.map((item) => notificationsApi.deleteOne(item.notification_id)));
      addNotification({
        type: 'success',
        title: t('notificationsPage.bulkDeleteTitle', 'Batch Delete Complete'),
        message: t(
          'notificationsPage.bulkDeleteMessage',
          '{{count}} notifications deleted',
          { count: selectedRows.length }
        ),
      });
      setSelectedIds(new Set());
      await refreshData();
    } finally {
      setIsMutating(false);
    }
  };

  const toggleSelectAllOnPage = () => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (allOnPageSelected) {
        notifications.forEach((item) => next.delete(item.notification_id));
      } else {
        notifications.forEach((item) => next.add(item.notification_id));
      }
      return next;
    });
  };

  const formatTimestamp = (value?: string) => {
    if (!value) return '—';
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    const locale = i18n.language.startsWith('zh') ? 'zh-CN' : 'en-US';
    return date.toLocaleString(locale, {
      hour12: false,
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  };

  const handleOpenLocalAction = (notification: LocalNotification) => {
    if (!notification.actionUrl) return;

    if (!notification.read) {
      markLocalAsRead(notification.id);
    }

    if (/^https?:\/\//.test(notification.actionUrl)) {
      window.open(notification.actionUrl, '_blank', 'noopener,noreferrer');
      return;
    }

    navigate(notification.actionUrl);
  };

  const handleMarkLocalRead = (notification: LocalNotification) => {
    if (notification.read) return;
    markLocalAsRead(notification.id);
  };

  const handleDeleteLocal = (notification: LocalNotification) => {
    if (!confirm(t('notificationsPage.confirmDeleteLocal', 'Delete this local notification?'))) {
      return;
    }
    removeLocalNotification(notification.id);
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-start gap-3">
          <div className="p-3 rounded-xl bg-gradient-to-br from-emerald-500/15 to-teal-500/20">
            <Bell className="w-6 h-6 text-emerald-500" />
          </div>
          <div>
            <h1 className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
              {t('notificationsPage.title', 'Notification Center')}
            </h1>
            <p className="text-sm text-zinc-600 dark:text-zinc-400 mt-1">
              {t(
                'notificationsPage.subtitle',
                'Process high-volume alerts and historical events with server-side pagination'
              )}
            </p>
          </div>
        </div>
        <button
          onClick={() => {
            void refreshData();
          }}
          disabled={isLoading || isMutating}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-zinc-300 dark:border-zinc-700 text-sm text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin' : ''}`} />
          {t('notificationsPage.refresh', 'Refresh')}
        </button>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <GlassPanel className="p-4">
          <p className="text-xs uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
            {t('notificationsPage.metrics.total', 'Total')}
          </p>
          <p className="mt-2 text-2xl font-semibold text-zinc-900 dark:text-zinc-100">
            {effectiveTotal}
          </p>
        </GlassPanel>
        <GlassPanel className="p-4">
          <p className="text-xs uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
            {t('notificationsPage.metrics.unread', 'Unread')}
          </p>
          <p className="mt-2 text-2xl font-semibold text-emerald-600 dark:text-emerald-400">
            {effectiveUnreadCount}
          </p>
        </GlassPanel>
        <GlassPanel className="p-4">
          <p className="text-xs uppercase tracking-widest text-zinc-500 dark:text-zinc-400">
            {t('notificationsPage.metrics.pageRange', 'Current Range')}
          </p>
          <p className="mt-2 text-lg font-semibold text-zinc-900 dark:text-zinc-100">
            {pageRangeLabel}
          </p>
        </GlassPanel>
      </div>

      <GlassPanel className="p-4 space-y-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-400" />
            <input
              value={searchInput}
              onChange={(e) => setSearchInput(e.target.value)}
              placeholder={t('notificationsPage.searchPlaceholder', 'Search title or message')}
              className="w-full pl-9 pr-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg text-sm text-zinc-900 dark:text-zinc-100 placeholder-zinc-400"
            />
          </div>

          <div className="flex items-center rounded-lg border border-zinc-300 dark:border-zinc-700 overflow-hidden">
            <button
              onClick={() => setStatusFilter('all')}
              className={`px-3 py-2 text-sm ${
                statusFilter === 'all'
                  ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                  : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
              }`}
            >
              {t('notificationsPage.status.all', 'All')}
            </button>
            <button
              onClick={() => setStatusFilter('unread')}
              className={`px-3 py-2 text-sm border-l border-zinc-300 dark:border-zinc-700 ${
                statusFilter === 'unread'
                  ? 'bg-emerald-500/20 text-emerald-700 dark:text-emerald-300'
                  : 'text-zinc-600 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800'
              }`}
            >
              {t('notificationsPage.status.unread', 'Unread')}
            </button>
          </div>

          <select
            value={severityFilter}
            onChange={(e) =>
              setSeverityFilter(e.target.value as NotificationSeverity | 'all')
            }
            className="px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg text-sm text-zinc-700 dark:text-zinc-200"
          >
            <option value="all">{t('notificationsPage.severity.all', 'All severities')}</option>
            <option value="info">{t('notificationsPage.severity.info', 'Info')}</option>
            <option value="success">{t('notificationsPage.severity.success', 'Success')}</option>
            <option value="warning">{t('notificationsPage.severity.warning', 'Warning')}</option>
            <option value="error">{t('notificationsPage.severity.error', 'Error')}</option>
          </select>

          <select
            value={String(pageSize)}
            onChange={(e) => setPageSize(Number(e.target.value))}
            className="px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg text-sm text-zinc-700 dark:text-zinc-200"
          >
            {PAGE_SIZE_OPTIONS.map((size) => (
              <option key={size} value={size}>
                {t('notificationsPage.pageSize', '{{size}} / page', { size })}
              </option>
            ))}
          </select>
        </div>

        {!isLocalFallbackMode && selectedIds.size > 0 && (
          <div className="flex flex-wrap items-center justify-between gap-3 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-900/20 border border-emerald-200 dark:border-emerald-800">
            <p className="text-sm text-emerald-700 dark:text-emerald-300">
              {t('notificationsPage.selectedCount', '{{count}} selected', { count: selectedIds.size })}
            </p>
            <div className="flex items-center gap-2">
              <button
                onClick={() => {
                  void handleBulkMarkRead();
                }}
                disabled={isMutating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-emerald-300 dark:border-emerald-700 text-xs text-emerald-700 dark:text-emerald-300 hover:bg-emerald-100 dark:hover:bg-emerald-900/30 disabled:opacity-50"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                {t('notificationsPage.bulkMarkRead', 'Mark Selected Read')}
              </button>
              <button
                onClick={() => {
                  void handleBulkDelete();
                }}
                disabled={isMutating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-300 dark:border-red-700 text-xs text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('notificationsPage.bulkDelete', 'Delete Selected')}
              </button>
            </div>
          </div>
        )}
      </GlassPanel>

      <GlassPanel className="p-4">
        {!isLocalFallbackMode && (
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <label className="inline-flex items-center gap-2 text-sm text-zinc-600 dark:text-zinc-300">
              <input
                type="checkbox"
                checked={allOnPageSelected}
                onChange={toggleSelectAllOnPage}
                className="h-4 w-4 accent-emerald-500"
              />
              {t('notificationsPage.selectPage', 'Select current page')}
            </label>
            <div className="flex flex-wrap items-center gap-2">
              <button
                onClick={() => {
                  void handleMarkAllRead();
                }}
                disabled={isMutating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-300 dark:border-zinc-700 text-xs text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
              >
                <CheckCheck className="w-3.5 h-3.5" />
                {t('notificationsPage.markAllRead', 'Mark All Read')}
              </button>
              <button
                onClick={() => {
                  void handleClear('read');
                }}
                disabled={isMutating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-300 dark:border-zinc-700 text-xs text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('notificationsPage.clearRead', 'Clear Read')}
              </button>
              <button
                onClick={() => {
                  void handleClear('all');
                }}
                disabled={isMutating}
                className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-300 dark:border-red-700 text-xs text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
              >
                <Trash2 className="w-3.5 h-3.5" />
                {t('notificationsPage.clearAll', 'Clear All')}
              </button>
            </div>
          </div>
        )}

        {isLocalFallbackMode && (
          <div className="mb-4 rounded-lg border border-amber-300/70 dark:border-amber-600/50 bg-amber-50/60 dark:bg-amber-900/20 px-3 py-2">
            <p className="text-sm font-medium text-amber-700 dark:text-amber-300">
              {t('notificationsPage.localHistoryTitle', 'Showing local history records')}
            </p>
            <p className="mt-1 text-xs text-amber-700/90 dark:text-amber-300/90">
              {t(
                'notificationsPage.localHistoryHint',
                'The server returned no records for current filters. These notifications come from local browser storage.'
              )}
            </p>
          </div>
        )}

        {isLoading ? (
          <div className="py-12 flex items-center justify-center gap-2 text-zinc-600 dark:text-zinc-400">
            <RefreshCw className="w-4 h-4 animate-spin" />
            <span>{t('notificationsPage.loading', 'Loading notifications...')}</span>
          </div>
        ) : errorMessage ? (
          <div className="py-12 text-center text-sm text-red-600 dark:text-red-400">
            {errorMessage}
          </div>
        ) : isLocalFallbackMode ? (
          <div className="space-y-3">
            {localPageNotifications.map((notification) => {
              const severityStyle =
                severityStyleMap[notification.type] || severityStyleMap.info;
              const SeverityIcon = severityStyle.icon;

              return (
                <div
                  key={notification.id}
                  className={`p-4 rounded-xl border ${
                    notification.read
                      ? 'border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/40'
                      : 'border-emerald-300/70 dark:border-emerald-700/50 bg-emerald-50/60 dark:bg-emerald-900/15'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${severityStyle.badgeClass}`}
                        >
                          <SeverityIcon className="w-3 h-3" />
                          {t(severityStyle.labelKey, severityStyle.fallback)}
                        </span>
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          {t('notificationsPage.localSourceTag', 'Local')}
                        </span>
                        {!notification.read && (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            {t('notificationsPage.unreadBadge', 'Unread')}
                          </span>
                        )}
                      </div>

                      <h3 className="mt-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                        {notification.title}
                      </h3>
                      <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap break-words">
                        {notification.message}
                      </p>

                      <div className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                        <span>
                          {t('notificationsPage.createdAt', 'Created')}:{' '}
                          {formatTimestamp(notification.timestamp)}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {notification.actionUrl && (
                          <button
                            onClick={() => handleOpenLocalAction(notification)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-emerald-300 dark:border-emerald-700 text-xs text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/25"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                            {notification.actionLabel || t('notificationsPage.open', 'Open')}
                          </button>
                        )}
                        {!notification.read && (
                          <button
                            onClick={() => handleMarkLocalRead(notification)}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-300 dark:border-zinc-700 text-xs text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800"
                          >
                            <CheckCheck className="w-3.5 h-3.5" />
                            {t('notificationsPage.markRead', 'Mark Read')}
                          </button>
                        )}
                        <button
                          onClick={() => handleDeleteLocal(notification)}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-300 dark:border-red-700 text-xs text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          {t('notificationsPage.delete', 'Delete')}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        ) : notifications.length === 0 ? (
          <div className="py-12 text-center text-zinc-600 dark:text-zinc-400">
            <Bell className="w-10 h-10 mx-auto mb-3 text-zinc-400" />
            <p>{t('notificationsPage.empty', 'No notifications found')}</p>
          </div>
        ) : (
          <div className="space-y-3">
            {notifications.map((notification) => {
              const severityStyle =
                severityStyleMap[notification.severity] || severityStyleMap.info;
              const SeverityIcon = severityStyle.icon;
              const isPending = pendingIds.has(notification.notification_id);

              return (
                <div
                  key={notification.notification_id}
                  className={`p-4 rounded-xl border ${
                    notification.is_read
                      ? 'border-zinc-200 dark:border-zinc-700 bg-white dark:bg-zinc-900/40'
                      : 'border-emerald-300/70 dark:border-emerald-700/50 bg-emerald-50/60 dark:bg-emerald-900/15'
                  }`}
                >
                  <div className="flex items-start gap-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(notification.notification_id)}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setSelectedIds((prev) => {
                          const next = new Set(prev);
                          if (checked) {
                            next.add(notification.notification_id);
                          } else {
                            next.delete(notification.notification_id);
                          }
                          return next;
                        });
                      }}
                      className="h-4 w-4 mt-1 accent-emerald-500"
                    />

                    <div className="flex-1 min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <span
                          className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium ${severityStyle.badgeClass}`}
                        >
                          <SeverityIcon className="w-3 h-3" />
                          {t(severityStyle.labelKey, severityStyle.fallback)}
                        </span>
                        <span className="text-xs text-zinc-500 dark:text-zinc-400">
                          {notification.notification_type}
                        </span>
                        {!notification.is_read && (
                          <span className="inline-flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
                            {t('notificationsPage.unreadBadge', 'Unread')}
                          </span>
                        )}
                      </div>

                      <h3 className="mt-2 text-sm font-semibold text-zinc-900 dark:text-zinc-100">
                        {notification.title}
                      </h3>
                      <p className="mt-1 text-sm text-zinc-700 dark:text-zinc-300 whitespace-pre-wrap break-words">
                        {notification.message}
                      </p>

                      <div className="mt-2 text-xs text-zinc-500 dark:text-zinc-400 flex flex-wrap gap-x-4 gap-y-1">
                        <span>
                          {t('notificationsPage.createdAt', 'Created')}: {formatTimestamp(notification.created_at)}
                        </span>
                        <span>
                          {t('notificationsPage.readAt', 'Read')}: {formatTimestamp(notification.read_at)}
                        </span>
                      </div>

                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        {notification.action_url && (
                          <button
                            onClick={() => {
                              void handleOpenAction(notification);
                            }}
                            disabled={isPending || isMutating}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-emerald-300 dark:border-emerald-700 text-xs text-emerald-700 dark:text-emerald-300 hover:bg-emerald-50 dark:hover:bg-emerald-900/25 disabled:opacity-50"
                          >
                            <ExternalLink className="w-3.5 h-3.5" />
                            {notification.action_label || t('notificationsPage.open', 'Open')}
                          </button>
                        )}
                        {!notification.is_read && (
                          <button
                            onClick={() => {
                              void handleMarkRead(notification);
                            }}
                            disabled={isPending || isMutating}
                            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-zinc-300 dark:border-zinc-700 text-xs text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
                          >
                            <CheckCheck className="w-3.5 h-3.5" />
                            {t('notificationsPage.markRead', 'Mark Read')}
                          </button>
                        )}
                        <button
                          onClick={() => {
                            void handleDeleteOne(notification);
                          }}
                          disabled={isPending || isMutating}
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md border border-red-300 dark:border-red-700 text-xs text-red-700 dark:text-red-300 hover:bg-red-50 dark:hover:bg-red-900/20 disabled:opacity-50"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                          {t('notificationsPage.delete', 'Delete')}
                        </button>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        )}

        <div className="mt-5 pt-4 border-t border-zinc-200 dark:border-zinc-700 flex items-center justify-between">
          <p className="text-xs text-zinc-500 dark:text-zinc-400">
            {paginationSummaryLabel}
          </p>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page <= 1 || isLoading}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              {t('notificationsPage.prevPage', 'Prev')}
            </button>
            <span className="text-xs text-zinc-600 dark:text-zinc-300">
              {page} / {totalPages}
            </span>
            <button
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={page >= totalPages || isLoading}
              className="inline-flex items-center gap-1 px-2.5 py-1.5 text-xs rounded-md border border-zinc-300 dark:border-zinc-700 text-zinc-700 dark:text-zinc-200 hover:bg-zinc-100 dark:hover:bg-zinc-800 disabled:opacity-50"
            >
              {t('notificationsPage.nextPage', 'Next')}
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </GlassPanel>
    </div>
  );
};

export default Notifications;
