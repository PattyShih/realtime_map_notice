import { useState, useEffect, useRef } from "react";
import type { EventNotification, MapEvent } from "../types/api";
import { createNotificationSocket } from "../services/websocket";

export function useNotificationSocket(userId: string | null) {
  const [connected, setConnected] = useState(false);
  const [latestNotification, setLatestNotification] =
    useState<EventNotification | null>(null);
  const [events, setEvents] = useState<MapEvent[]>([]);
  const eventsRef = useRef<MapEvent[]>([]);

  useEffect(() => {
    if (!userId) return;

    const socket = createNotificationSocket(
      userId,
      (notification) => {
        setLatestNotification(notification);
        const mapEvent: MapEvent = {
          id: notification.event_id,
          title: notification.title,
          message: notification.message,
          latitude: notification.latitude,
          longitude: notification.longitude,
          severity: notification.severity,
          distance_meters: notification.distance_meters,
          created_at: new Date().toISOString(),
        };
        eventsRef.current = [mapEvent, ...eventsRef.current].slice(0, 50);
        setEvents(eventsRef.current);
      },
      setConnected,
    );

    return () => socket.destroy();
  }, [userId]);

  return { connected, latestNotification, events };
}