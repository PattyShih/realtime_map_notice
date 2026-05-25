import type { EventNotification } from "../types/api";

const WS_BASE = import.meta.env.VITE_NOTIFICATION_WS_URL ?? "ws://localhost:8003";

type NotificationCallback = (notification: EventNotification) => void;
type WebSocketControlMessage = { type: "ping" | "pong" };

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isControlMessage(value: unknown): value is WebSocketControlMessage {
  return (
    isRecord(value) &&
    typeof value.type === "string" &&
    (value.type === "ping" || value.type === "pong")
  );
}

function isEventNotification(value: unknown): value is EventNotification {
  return (
    isRecord(value) &&
    typeof value.event_id === "string" &&
    typeof value.title === "string" &&
    typeof value.message === "string" &&
    typeof value.latitude === "number" &&
    typeof value.longitude === "number" &&
    typeof value.severity === "string"
  );
}

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
        const message: unknown = JSON.parse(event.data);
        if (isControlMessage(message)) {
          if (message.type === "ping" && ws?.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({ type: "pong" }));
          }
          return;
        }

        if (isEventNotification(message)) {
          onNotification(message);
        }
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
