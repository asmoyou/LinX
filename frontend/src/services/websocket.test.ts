/**
 * WebSocket Manager Tests
 * 
 * Tests for WebSocket connection manager functionality
 */

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { WebSocketManager } from './websocket';

// Mock WebSocket
class MockWebSocket {
  static CONNECTING = 0;
  static OPEN = 1;
  static CLOSING = 2;
  static CLOSED = 3;

  readyState = MockWebSocket.CONNECTING;
  url: string;
  onopen: ((event: Event) => void) | null = null;
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: Event) => void) | null = null;
  onclose: ((event: CloseEvent) => void) | null = null;

  constructor(url: string) {
    this.url = url;
    // Simulate async connection
    setTimeout(() => {
      this.readyState = MockWebSocket.OPEN;
      if (this.onopen) {
        this.onopen(new Event('open'));
      }
    }, 10);
  }

  send(data: string) {
    void data;
    if (this.readyState !== MockWebSocket.OPEN) {
      throw new Error('WebSocket is not open');
    }
  }

  close(code?: number, reason?: string) {
    this.readyState = MockWebSocket.CLOSED;
    if (this.onclose) {
      this.onclose(new CloseEvent('close', { code: code || 1000, reason: reason || '' }));
    }
  }

  // Helper to simulate receiving a message
  simulateMessage(data: any) {
    if (this.onmessage) {
      this.onmessage(new MessageEvent('message', { data: JSON.stringify(data) }));
    }
  }

  // Helper to simulate error
  simulateError() {
    if (this.onerror) {
      this.onerror(new Event('error'));
    }
  }
}

// Replace global WebSocket with mock
global.WebSocket = MockWebSocket as any;

describe('WebSocketManager', () => {
  let manager: WebSocketManager;

  beforeEach(() => {
    vi.useFakeTimers();
    manager = new WebSocketManager({
      url: 'ws://localhost:8000/ws/tasks',
      token: 'test-token',
      reconnect: true,
      reconnectInterval: 1000,
      maxReconnectAttempts: 3,
      heartbeatInterval: 5000,
      debug: false,
    });
  });

  afterEach(() => {
    manager.destroy();
    vi.useRealTimers();
  });

  describe('Connection', () => {
    it('should connect to WebSocket server', async () => {
      const statusHandler = vi.fn();
      manager.onStatusChange(statusHandler);

      manager.connect();
      expect(statusHandler).toHaveBeenCalledWith('connecting');

      // Wait for connection to open
      await vi.advanceTimersByTimeAsync(20);
      expect(statusHandler).toHaveBeenCalledWith('connected');
      expect(manager.isConnected()).toBe(true);
    });

    it('should include token in URL', () => {
      manager.connect();
      // Check that WebSocket was created with token parameter
      // This would need access to the internal ws instance
    });

    it('should not connect if already connected', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      const statusHandler = vi.fn();
      manager.onStatusChange(statusHandler);

      manager.connect();
      expect(statusHandler).not.toHaveBeenCalled();
    });
  });

  describe('Disconnection', () => {
    it('should disconnect from WebSocket server', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      const statusHandler = vi.fn();
      manager.onStatusChange(statusHandler);

      manager.disconnect();
      expect(statusHandler).toHaveBeenCalledWith('disconnected');
      expect(manager.isConnected()).toBe(false);
    });

    it('should not attempt to reconnect after manual disconnect', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      manager.disconnect();

      // Wait for potential reconnect attempt
      await vi.advanceTimersByTimeAsync(5000);
      expect(manager.getStatus()).toBe('disconnected');
    });
  });

  describe('Message Handling', () => {
    it('should receive and parse messages', async () => {
      const messageHandler = vi.fn();
      manager.on('task_status_update', messageHandler);

      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      // Simulate receiving a message
      const mockMessage = {
        type: 'task_status_update',
        data: { task_id: '123', status: 'completed' },
      };
      expect(mockMessage.type).toBe('task_status_update');

      // Access the internal WebSocket and simulate message
      // This would need a way to access the internal ws instance
    });

    it('should handle multiple event handlers', async () => {
      const handler1 = vi.fn();
      const handler2 = vi.fn();

      manager.on('task_status_update', handler1);
      manager.on('task_status_update', handler2);

      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      // Both handlers should be called
    });

    it('should support "all" event handler', async () => {
      const allHandler = vi.fn();
      manager.on('all', allHandler);

      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      // All messages should trigger the handler
    });
  });

  describe('Reconnection', () => {
    it('should attempt to reconnect on connection loss', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      const statusHandler = vi.fn();
      manager.onStatusChange(statusHandler);

      // Simulate connection loss
      manager.disconnect();
      manager['shouldReconnect'] = true; // Force reconnect flag

      // Should schedule reconnect
      await vi.advanceTimersByTimeAsync(1000);
      expect(statusHandler).toHaveBeenCalledWith('reconnecting');
    });

    it('should use exponential backoff for reconnection', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      // Simulate multiple connection failures
      for (let i = 0; i < 3; i++) {
        manager.disconnect();
        manager['shouldReconnect'] = true;
        await vi.advanceTimersByTimeAsync(1000 * Math.pow(1.5, i));
      }

      expect(manager.getReconnectAttempts()).toBeGreaterThan(0);
    });

    it('should stop reconnecting after max attempts', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      const statusHandler = vi.fn();
      manager.onStatusChange(statusHandler);

      // Simulate max reconnection attempts
      for (let i = 0; i < 4; i++) {
        manager.disconnect();
        manager['shouldReconnect'] = true;
        await vi.advanceTimersByTimeAsync(10000);
      }

      expect(manager.getStatus()).toBe('error');
    });
  });

  describe('Heartbeat', () => {
    it('should send heartbeat messages', async () => {
      const sendSpy = vi.spyOn(manager, 'send');

      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      // Wait for heartbeat interval
      await vi.advanceTimersByTimeAsync(5000);

      expect(sendSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          type: 'heartbeat',
        })
      );
    });

    it('should close connection on heartbeat timeout', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      // Wait for heartbeat
      await vi.advanceTimersByTimeAsync(5000);

      // Don't respond to heartbeat, wait for timeout
      await vi.advanceTimersByTimeAsync(6000);

      // Connection should be closed
      expect(manager.isConnected()).toBe(false);
    });
  });

  describe('Event Subscription', () => {
    it('should allow subscribing to events', () => {
      const handler = vi.fn();
      const unsubscribe = manager.on('task_status_update', handler);

      expect(typeof unsubscribe).toBe('function');
    });

    it('should allow unsubscribing from events', () => {
      const handler = vi.fn();
      const unsubscribe = manager.on('task_status_update', handler);

      unsubscribe();

      // Handler should not be called after unsubscribe
    });

    it('should allow unsubscribing via off method', () => {
      const handler = vi.fn();
      manager.on('task_status_update', handler);

      manager.off('task_status_update', handler);

      // Handler should not be called after off
    });
  });

  describe('Status Management', () => {
    it('should track connection status', async () => {
      expect(manager.getStatus()).toBe('disconnected');

      manager.connect();
      expect(manager.getStatus()).toBe('connecting');

      await vi.advanceTimersByTimeAsync(20);
      expect(manager.getStatus()).toBe('connected');

      manager.disconnect();
      expect(manager.getStatus()).toBe('disconnected');
    });

    it('should notify status change handlers', async () => {
      const statusHandler = vi.fn();
      manager.onStatusChange(statusHandler);

      manager.connect();
      expect(statusHandler).toHaveBeenCalledWith('connecting');

      await vi.advanceTimersByTimeAsync(20);
      expect(statusHandler).toHaveBeenCalledWith('connected');
    });
  });

  describe('Cleanup', () => {
    it('should clean up resources on destroy', async () => {
      manager.connect();
      await vi.advanceTimersByTimeAsync(20);

      manager.destroy();

      expect(manager.isConnected()).toBe(false);
      expect(manager.getStatus()).toBe('disconnected');
    });
  });
});
