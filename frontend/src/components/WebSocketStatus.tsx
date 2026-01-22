/**
 * WebSocket Connection Status Indicator
 * 
 * Displays the current WebSocket connection status with visual feedback
 * 
 * References:
 * - Task 6.12.9: Add connection status indicator in UI
 */

import { Wifi, WifiOff, RefreshCw, AlertCircle } from 'lucide-react';
import { useWebSocket } from '../hooks/useWebSocket';
import type { WebSocketStatus } from '../services/websocket';

interface WebSocketStatusProps {
  className?: string;
  showText?: boolean;
  showReconnectAttempts?: boolean;
}

const statusConfig: Record<WebSocketStatus, {
  icon: typeof Wifi;
  label: string;
  color: string;
  bgColor: string;
  pulseColor?: string;
}> = {
  connected: {
    icon: Wifi,
    label: 'Connected',
    color: 'text-green-600 dark:text-green-400',
    bgColor: 'bg-green-100 dark:bg-green-900/30',
    pulseColor: 'bg-green-500',
  },
  connecting: {
    icon: RefreshCw,
    label: 'Connecting...',
    color: 'text-blue-600 dark:text-blue-400',
    bgColor: 'bg-blue-100 dark:bg-blue-900/30',
  },
  reconnecting: {
    icon: RefreshCw,
    label: 'Reconnecting...',
    color: 'text-yellow-600 dark:text-yellow-400',
    bgColor: 'bg-yellow-100 dark:bg-yellow-900/30',
  },
  disconnected: {
    icon: WifiOff,
    label: 'Disconnected',
    color: 'text-gray-600 dark:text-gray-400',
    bgColor: 'bg-gray-100 dark:bg-gray-900/30',
  },
  error: {
    icon: AlertCircle,
    label: 'Connection Error',
    color: 'text-red-600 dark:text-red-400',
    bgColor: 'bg-red-100 dark:bg-red-900/30',
  },
};

export function WebSocketStatus({
  className = '',
  showText = true,
  showReconnectAttempts = true,
}: WebSocketStatusProps) {
  const { status, reconnectAttempts } = useWebSocket({ autoConnect: false });

  const config = statusConfig[status];
  const Icon = config.icon;
  const isAnimating = status === 'connecting' || status === 'reconnecting';

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {/* Status indicator */}
      <div className="relative">
        <div className={`p-1.5 rounded-lg ${config.bgColor}`}>
          <Icon
            className={`w-4 h-4 ${config.color} ${isAnimating ? 'animate-spin' : ''}`}
          />
        </div>
        
        {/* Pulse animation for connected state */}
        {status === 'connected' && config.pulseColor && (
          <span className="absolute top-0 right-0 flex h-3 w-3">
            <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${config.pulseColor} opacity-75`}></span>
            <span className={`relative inline-flex rounded-full h-3 w-3 ${config.pulseColor}`}></span>
          </span>
        )}
      </div>

      {/* Status text */}
      {showText && (
        <div className="flex flex-col">
          <span className={`text-sm font-medium ${config.color}`}>
            {config.label}
          </span>
          {showReconnectAttempts && reconnectAttempts > 0 && (
            <span className="text-xs text-gray-500 dark:text-gray-400">
              Attempt {reconnectAttempts}
            </span>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Compact WebSocket status indicator (icon only with tooltip)
 */
export function WebSocketStatusCompact({ className = '' }: { className?: string }) {
  const { status } = useWebSocket({ autoConnect: false });
  const config = statusConfig[status];
  const Icon = config.icon;
  const isAnimating = status === 'connecting' || status === 'reconnecting';

  return (
    <div
      className={`relative group ${className}`}
      title={config.label}
    >
      <div className={`p-2 rounded-lg ${config.bgColor} transition-colors`}>
        <Icon
          className={`w-4 h-4 ${config.color} ${isAnimating ? 'animate-spin' : ''}`}
        />
      </div>

      {/* Pulse animation for connected state */}
      {status === 'connected' && config.pulseColor && (
        <span className="absolute top-0 right-0 flex h-2 w-2">
          <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${config.pulseColor} opacity-75`}></span>
          <span className={`relative inline-flex rounded-full h-2 w-2 ${config.pulseColor}`}></span>
        </span>
      )}

      {/* Tooltip */}
      <div className="absolute bottom-full right-0 mb-2 hidden group-hover:block z-50">
        <div className="bg-gray-900 dark:bg-gray-800 text-white text-xs rounded-lg py-1 px-2 whitespace-nowrap">
          {config.label}
          <div className="absolute top-full right-2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-transparent border-t-gray-900 dark:border-t-gray-800"></div>
        </div>
      </div>
    </div>
  );
}
