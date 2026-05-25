import { useState, useCallback, useEffect } from "react";
import MapView from "./components/MapView";
import EventForm from "./components/EventForm";
import NotificationBanner from "./components/NotificationBanner";
import { useGeolocation } from "./hooks/useGeolocation";
import { useNotificationSocket } from "./hooks/useNotificationSocket";
import { updateLocation } from "./services/locationApi";
import { createEvent } from "./services/eventApi";
import type { EventCreate } from "./types/api";

const USER_ID = `u-${Date.now()}`;

export default function App() {
  const geolocation = useGeolocation();
  const {
    connected,
    latestNotification,
    events: wsEvents,
  } = useNotificationSocket(USER_ID);

  const [showForm, setShowForm] = useState(false);
  const [pendingLocation, setPendingLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());
  const [formError, setFormError] = useState<string | null>(null);
  const [focusLocation, setFocusLocation] = useState<{
    latitude: number;
    longitude: number;
  } | null>(null);

  // Local events (created by this user via the form)
  const [localEvents, setLocalEvents] = useState<
    { id: string; title: string; latitude: number; longitude: number; severity: string }[]
  >([]);

  // Combine ws events + local events for map display
  const allEvents = [
    ...wsEvents,
    ...localEvents.map((e) => ({
      id: e.id,
      title: e.title,
      message: "",
      latitude: e.latitude,
      longitude: e.longitude,
      severity: e.severity as "info" | "urgent",
      distance_meters: null,
      created_at: "",
    })),
  ];

  // Periodic location upload
  useEffect(() => {
    const uploadTimer = setInterval(() => {
      if (geolocation.latitude !== null && geolocation.longitude !== null) {
        updateLocation({
          user_id: USER_ID,
          latitude: geolocation.latitude,
          longitude: geolocation.longitude,
        }).catch(() => {
          // silent retry next interval
        });
      }
    }, 1500);
    return () => clearInterval(uploadTimer);
  }, [geolocation.latitude, geolocation.longitude]);

  const handleMapClick = useCallback(
    (lat: number, lng: number) => {
      setPendingLocation({ latitude: lat, longitude: lng });
      setShowForm(true);
      setFormError(null);
    },
    [],
  );

  const handleFormSubmit = useCallback(
    async (event: EventCreate) => {
      setSubmitting(true);
      setFormError(null);
      try {
        const result = await createEvent(event);
        setStatusMsg(
          `Event posted! Delivered to ${result.delivered_count} nearby user(s).`,
        );
        setLocalEvents((prev) => [
          {
            id: result.event_id,
            title: event.title,
            latitude: event.latitude,
            longitude: event.longitude,
            severity: event.severity,
          },
          ...prev.slice(0, 20),
        ]);
        setShowForm(false);
        setPendingLocation(null);
      } catch {
        setFormError("Failed to create event. Is the backend running?");
      } finally {
        setSubmitting(false);
      }
    },
    [],
  );

  const handleFormCancel = useCallback(() => {
    setShowForm(false);
    setPendingLocation(null);
    setFormError(null);
  }, []);

  const activeNotifications =
    latestNotification && !dismissedIds.has(latestNotification.event_id)
      ? [latestNotification]
      : [];

  const handleNotificationView = useCallback(
    (lat: number, lng: number) => {
      setFocusLocation({ latitude: lat, longitude: lng });
    },
    [],
  );

  return (
    <div className="app-container">
      {/* Status bar */}
      <div className="status-bar">
        <span className={`connection-dot ${connected ? "connected" : "disconnected"}`} />
        <span>{connected ? "Live" : "Disconnected"}</span>
        {geolocation.error && (
          <span className="geo-warning">GPS: {geolocation.error}</span>
        )}
      </div>

      {/* Map */}
      <MapView
        userLocation={
          geolocation.latitude !== null && geolocation.longitude !== null
            ? {
                latitude: geolocation.latitude,
                longitude: geolocation.longitude,
              }
            : null
        }
        events={allEvents}
        onMapClick={handleMapClick}
        pendingLocation={pendingLocation}
        focusLocation={focusLocation}
      />

      {/* Event form modal */}
      {showForm && pendingLocation && (
        <EventForm
          latitude={pendingLocation.latitude}
          longitude={pendingLocation.longitude}
          onSubmit={handleFormSubmit}
          submitting={submitting}
          onCancel={handleFormCancel}
        />
      )}

      {/* Form error */}
      {formError && (
        <div className="form-error-banner">
          <span>{formError}</span>
          <button onClick={() => setFormError(null)}>Dismiss</button>
        </div>
      )}

      {/* Notification banners */}
      {activeNotifications.map((n) => (
        <NotificationBanner
          key={n.event_id}
          notification={n}
          onView={handleNotificationView}
          onDismiss={() =>
            setDismissedIds((prev) => new Set(prev).add(n.event_id))
          }
        />
      ))}

      {/* Status message toast */}
      {statusMsg && (
        <div className="toast" onClick={() => setStatusMsg(null)}>
          {statusMsg}
        </div>
      )}
    </div>
  );
}
