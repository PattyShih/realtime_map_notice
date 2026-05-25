import type { EventNotification } from "../types/api";

interface NotificationBannerProps {
  notification: EventNotification;
  onView: (lat: number, lng: number) => void;
  onDismiss: () => void;
}

export default function NotificationBanner({
  notification,
  onView,
  onDismiss,
}: NotificationBannerProps) {
  return (
    <div className={`notification-banner notification-${notification.severity}`}>
      <div className="notification-content">
        <span className="notification-badge">
          {notification.severity === "urgent" ? "URGENT" : "INFO"}
        </span>
        <div>
          <strong>{notification.title}</strong>
          <p>{notification.message}</p>
          {notification.distance_meters != null && (
            <small>{Math.round(notification.distance_meters)}m from you</small>
          )}
        </div>
      </div>
      <div className="notification-actions">
        <button
          onClick={() =>
            onView(notification.latitude, notification.longitude)
          }
        >
          View
        </button>
        <button onClick={onDismiss} className="dismiss-btn">
          Dismiss
        </button>
      </div>
    </div>
  );
}