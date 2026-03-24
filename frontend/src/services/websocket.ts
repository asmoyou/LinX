/**
 * WebSocket Connection Manager
 * 
 * Provides a robust WebSocket connection with:
 * - Automatic reconnection with exponential backoff
 * - Authentication support
 * - Heartbeat mechanism
 * - Event-based message handling
 * - Connection status tracking
 * - Error handling and fallback
 * 
 * References:
 * - Requirements 13, 15: Task Flow Visualization and API
 * - Task 6.12: WebSocket Real-Time Integration
 */

export type WebSocketStatus = 'connecting' | 'connected' | 'disconnected' | 'error' | 'reconnecting';

export type WebSocketMessageType =
  | 'agent_status_update'
  | 'task_status_update'
  | 'goal_status_update'
  | 'system_notification'
  | 'agent_created'
  | 'agent_deleted'
  | 'task_created'
  | 'task_completed'
  | 'task_failed'
  | 'task_flow_initial'
  | 'task_flow_update'
  | 'node_update'
  | 'relationship_added'
  | 'metrics_update'
  | 'heartbeat'
  | 'pong'
  | 'error'
  | 'echo'
  | 'retry_attempt'
  | 'error_feedback'
  | 'info';

export interface WebSocketMessage {
  type: WebSocketMessageType;
  data: any;
  timestamp?: string;
}

export type WebSocketEventHandler = (message: WebSocketMessage) => void;

export interface WebSocketConfig {
  url: string;
  token?: string;
  reconnect?: boolean;
  reconnectInterval?: number;
  reconnectDecay?: number;
  maxReconnectInterval?: number;
  maxReconnectAttempts?: number;
  heartbeatInterval?: number;
  heartbeatTimeout?: number;
  debug?: boolean;
}

type ResolvedWebSocketConfig = Omit<Required<WebSocketConfig>, "token"> & {
  token?: string;
};

export class WebSocketManager {
  private ws: WebSocket | null = null;
  private config: ResolvedWebSocketConfig;
  private status: WebSocketStatus = 'disconnected';
  private reconnectAttempts = 0;
  private reconnectTimeoutId: ReturnType<typeof setTimeout> | null = null;
  private heartbeatIntervalId: ReturnType<typeof setInterval> | null = null;
  private heartbeatTimeoutId: ReturnType<typeof setTimeout> | null = null;
  private lastHeartbeatTime: number = 0;
  private eventHandlers: Map<WebSocketMessageType | 'all', Set<WebSocketEventHandler>> = new Map();
  private statusChangeHandlers: Set<(status: WebSocketStatus) => void> = new Set();
  private shouldReconnect = true;

  constructor(config: WebSocketConfig) {
    this.config = {
      reconnect: true,
      reconnectInterval: 1000,
      reconnectDecay: 1.5,
      maxReconnectInterval: 30000,
      maxReconnectAttempts: 10,
      heartbeatInterval: 30000,
      heartbeatTimeout: 5000,
      debug: false,
      ...config,
    };

    this.log('WebSocketManager initialized', this.config);
  }

  /**
   * Connect to WebSocket server
   */
  public connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.log('Already connected');
      return;
    }

    if (this.ws?.readyState === WebSocket.CONNECTING) {
      this.log('Connection already in progress');
      return;
    }

    this.shouldReconnect = true;
    this.setStatus('connecting');
    this.log('Connecting to WebSocket...');

    try {
      const url = this.buildUrl();
      this.ws = new WebSocket(url);

      this.ws.onopen = this.handleOpen.bind(this);
      this.ws.onmessage = this.handleMessage.bind(this);
      this.ws.onerror = this.handleError.bind(this);
      this.ws.onclose = this.handleClose.bind(this);
    } catch (error) {
      this.log('Failed to create WebSocket connection', error);
      this.setStatus('error');
      this.scheduleReconnect();
    }
  }

  /**
   * Disconnect from WebSocket server
   */
  public disconnect(): void {
    this.log('Disconnecting...');
    this.shouldReconnect = false;
    this.clearReconnectTimeout();
    this.stopHeartbeat();

    if (this.ws) {
      this.ws.close(1000, 'Client disconnect');
      this.ws = null;
    }

    this.setStatus('disconnected');
  }

  /**
   * Send a message to the server
   */
  public send(message: WebSocketMessage | string): boolean {
    if (this.ws?.readyState !== WebSocket.OPEN) {
      this.log('Cannot send message: WebSocket not connected');
      return false;
    }

    try {
      const data = typeof message === 'string' ? message : JSON.stringify(message);
      this.ws.send(data);
      this.log('Message sent', message);
      return true;
    } catch (error) {
      this.log('Failed to send message', error);
      return false;
    }
  }

  /**
   * Subscribe to specific message type
   */
  public on(type: WebSocketMessageType | 'all', handler: WebSocketEventHandler): () => void {
    if (!this.eventHandlers.has(type)) {
      this.eventHandlers.set(type, new Set());
    }
    this.eventHandlers.get(type)!.add(handler);

    // Return unsubscribe function
    return () => {
      this.eventHandlers.get(type)?.delete(handler);
    };
  }

  /**
   * Unsubscribe from specific message type
   */
  public off(type: WebSocketMessageType | 'all', handler: WebSocketEventHandler): void {
    this.eventHandlers.get(type)?.delete(handler);
  }

  /**
   * Subscribe to connection status changes
   */
  public onStatusChange(handler: (status: WebSocketStatus) => void): () => void {
    this.statusChangeHandlers.add(handler);

    // Return unsubscribe function
    return () => {
      this.statusChangeHandlers.delete(handler);
    };
  }

  /**
   * Get current connection status
   */
  public getStatus(): WebSocketStatus {
    return this.status;
  }

  /**
   * Check if connected
   */
  public isConnected(): boolean {
    return this.status === 'connected' && this.ws?.readyState === WebSocket.OPEN;
  }

  /**
   * Get reconnection attempts count
   */
  public getReconnectAttempts(): number {
    return this.reconnectAttempts;
  }

  /**
   * Get last heartbeat time
   */
  public getLastHeartbeatTime(): number {
    return this.lastHeartbeatTime;
  }

  /**
   * Handle WebSocket open event
   */
  private handleOpen(): void {
    this.log('WebSocket connected');
    this.setStatus('connected');
    this.reconnectAttempts = 0;
    this.clearReconnectTimeout();

    // Send initial subscription message
    this.send({
      type: 'agent_status_update',
      data: {
        type: 'subscribe',
        channels: ['agents', 'tasks', 'goals', 'notifications', 'metrics'],
      },
    });

    // Start heartbeat
    this.startHeartbeat();
  }

  /**
   * Handle WebSocket message event
   */
  private handleMessage(event: MessageEvent): void {
    try {
      const message: WebSocketMessage = JSON.parse(event.data);
      this.log('Message received', message);

      // Handle heartbeat response
      if (message.type === 'pong') {
        this.handleHeartbeatResponse();
        return;
      }

      // Emit to specific type handlers
      const typeHandlers = this.eventHandlers.get(message.type);
      if (typeHandlers) {
        typeHandlers.forEach((handler) => handler(message));
      }

      // Emit to 'all' handlers
      const allHandlers = this.eventHandlers.get('all');
      if (allHandlers) {
        allHandlers.forEach((handler) => handler(message));
      }
    } catch (error) {
      this.log('Failed to parse message', error);
    }
  }

  /**
   * Handle WebSocket error event
   */
  private handleError(event: Event): void {
    this.log('WebSocket error', event);
    this.setStatus('error');
  }

  /**
   * Handle WebSocket close event
   */
  private handleClose(event: CloseEvent): void {
    this.log('WebSocket closed', { code: event.code, reason: event.reason });
    this.stopHeartbeat();
    this.ws = null;

    if (this.shouldReconnect && this.config.reconnect) {
      this.setStatus('reconnecting');
      this.scheduleReconnect();
    } else {
      this.setStatus('disconnected');
    }
  }

  /**
   * Schedule reconnection attempt
   */
  private scheduleReconnect(): void {
    if (this.reconnectAttempts >= this.config.maxReconnectAttempts) {
      this.log('Max reconnection attempts reached');
      this.setStatus('error');
      this.shouldReconnect = false;
      return;
    }

    this.clearReconnectTimeout();

    // Calculate delay with exponential backoff
    const delay = Math.min(
      this.config.reconnectInterval * Math.pow(this.config.reconnectDecay, this.reconnectAttempts),
      this.config.maxReconnectInterval
    );

    this.reconnectAttempts++;
    this.log(`Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts}/${this.config.maxReconnectAttempts})`);

    this.reconnectTimeoutId = setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * Clear reconnection timeout
   */
  private clearReconnectTimeout(): void {
    if (this.reconnectTimeoutId) {
      clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
  }

  /**
   * Start heartbeat mechanism
   */
  private startHeartbeat(): void {
    this.stopHeartbeat();

    this.heartbeatIntervalId = setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.send({ type: 'heartbeat', data: { timestamp: Date.now() } });
        this.lastHeartbeatTime = Date.now();

        // Set timeout for heartbeat response
        this.heartbeatTimeoutId = setTimeout(() => {
          this.log('Heartbeat timeout - connection may be dead');
          this.ws?.close();
        }, this.config.heartbeatTimeout);
      }
    }, this.config.heartbeatInterval);
  }

  /**
   * Stop heartbeat mechanism
   */
  private stopHeartbeat(): void {
    if (this.heartbeatIntervalId) {
      clearInterval(this.heartbeatIntervalId);
      this.heartbeatIntervalId = null;
    }

    if (this.heartbeatTimeoutId) {
      clearTimeout(this.heartbeatTimeoutId);
      this.heartbeatTimeoutId = null;
    }
  }

  /**
   * Handle heartbeat response
   */
  private handleHeartbeatResponse(): void {
    if (this.heartbeatTimeoutId) {
      clearTimeout(this.heartbeatTimeoutId);
      this.heartbeatTimeoutId = null;
    }
    this.log('Heartbeat received');
  }

  /**
   * Build WebSocket URL with authentication
   */
  private buildUrl(): string {
    let url = this.config.url;

    // Add token as query parameter if provided
    if (this.config.token) {
      const separator = url.includes('?') ? '&' : '?';
      url = `${url}${separator}token=${this.config.token}`;
    }

    return url;
  }

  /**
   * Set connection status and notify handlers
   */
  private setStatus(status: WebSocketStatus): void {
    if (this.status !== status) {
      this.status = status;
      this.log(`Status changed: ${status}`);
      this.statusChangeHandlers.forEach((handler) => handler(status));
    }
  }

  /**
   * Log message (if debug enabled)
   */
  private log(message: string, data?: any): void {
    if (this.config.debug) {
      if (data !== undefined) {
        console.log(`[WebSocketManager] ${message}`, data);
      } else {
        console.log(`[WebSocketManager] ${message}`);
      }
    }
  }

  /**
   * Cleanup resources
   */
  public destroy(): void {
    this.log('Destroying WebSocketManager');
    this.disconnect();
    this.eventHandlers.clear();
    this.statusChangeHandlers.clear();
  }
}

// Singleton instance
let wsManagerInstance: WebSocketManager | null = null;

/**
 * Get or create WebSocket manager instance
 */
export function getWebSocketManager(config?: WebSocketConfig): WebSocketManager {
  if (!wsManagerInstance && config) {
    wsManagerInstance = new WebSocketManager(config);
  }

  if (!wsManagerInstance) {
    throw new Error('WebSocketManager not initialized. Provide config on first call.');
  }

  return wsManagerInstance;
}

/**
 * Destroy WebSocket manager instance
 */
export function destroyWebSocketManager(): void {
  if (wsManagerInstance) {
    wsManagerInstance.destroy();
    wsManagerInstance = null;
  }
}
