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
          {notification.severity === "urgent" ? "緊急" : "一般"}
        </span>
        <div>
          <strong>{notification.title}</strong>
          <p>{notification.message}</p>
          {notification.distance_meters != null && (
            <small>距離你 {Math.round(notification.distance_meters)} 公尺</small>
          )}
        </div>
      </div>
      <div className="notification-actions">
        <button
          onClick={() =>
            onView(notification.latitude, notification.longitude)
          }
        >
          查看
        </button>
        <button onClick={onDismiss} className="dismiss-btn">
          略過
        </button>
      </div>
    </div>
  );
}
