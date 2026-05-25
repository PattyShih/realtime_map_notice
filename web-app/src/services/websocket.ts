import type { EventNotification } from "../types/api";

const WS_BASE = import.meta.env.VITE_NOTIFICATION_WS_URL ?? "ws://localhost:8003";

type NotificationCallback = (notification: EventNotification) => void;

export function createNotificationSocket(
  userId: string,
  onNotification: NotificationCallback,
  onStatusChange?: (connected: boolean) => void,
) {
  let ws: WebSocket | null = null;
  let reconnectAttempt = 0;
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
  let destroyed = false;

  function connect() {
    if (destroyed) return;

    ws = new WebSocket(`${WS_BASE}/ws/${userId}`);

    ws.onopen = () => {
      reconnectAttempt = 0;
      onStatusChange?.(true);
    };

    ws.onmessage = (event) => {
      try {
        const notification: EventNotification = JSON.parse(event.data);
        onNotification(notification);
      } catch {
        // ignore malformed messages
      }
    };

    ws.onclose = () => {
      onStatusChange?.(false);
      if (!destroyed) {
        scheduleReconnect();
      }
    };

    ws.onerror = () => {
      ws?.close();
    };
  }

  function scheduleReconnect() {
    const delay = Math.min(1000 * 2 ** reconnectAttempt, 30000);
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(connect, delay);
  }

  connect();

  return {
    destroy() {
      destroyed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    },
  };
}