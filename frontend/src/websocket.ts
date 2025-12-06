/**
 * WebSocket client utilities for the reactive notebook
 */
import type { ClientMessage, ServerMessage } from './types';

export type MessageHandler = (message: ServerMessage) => void;

export interface WebSocketClient {
  send: (message: ClientMessage) => void;
  close: () => void;
  isConnected: () => boolean;
}

export function createWebSocketClient(
  url: string,
  onMessage: MessageHandler,
  onConnectionChange: (connected: boolean) => void
): WebSocketClient {
  let ws: WebSocket | null = null;
  let reconnectTimeout: ReturnType<typeof setTimeout> | null = null;
  let isConnected = false;

  function connect() {
    try {
      ws = new WebSocket(url);

      ws.onopen = () => {
        console.log('WebSocket connected');
        isConnected = true;
        onConnectionChange(true);
      };

      ws.onclose = () => {
        console.log('WebSocket disconnected');
        isConnected = false;
        onConnectionChange(false);
        
        // Attempt to reconnect after 2 seconds
        reconnectTimeout = setTimeout(() => {
          console.log('Attempting to reconnect...');
          connect();
        }, 2000);
      };

      ws.onerror = (error) => {
        console.error('WebSocket error:', error);
      };

      ws.onmessage = (event) => {
        try {
          const message: ServerMessage = JSON.parse(event.data);
          onMessage(message);
        } catch (error) {
          console.error('Failed to parse message:', error);
        }
      };
    } catch (error) {
      console.error('Failed to create WebSocket:', error);
      // Retry connection
      reconnectTimeout = setTimeout(connect, 2000);
    }
  }

  // Initial connection
  connect();

  return {
    send: (message: ClientMessage) => {
      if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify(message));
      } else {
        console.warn('WebSocket not connected, message not sent:', message);
      }
    },
    close: () => {
      if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
      }
      if (ws) {
        ws.close();
      }
    },
    isConnected: () => isConnected,
  };
}

