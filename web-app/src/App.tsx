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

type PickerMode = "idle" | "choosing" | "picking";

export default function App() {
  const geolocation = useGeolocation();
  const {
    connected,
    latestNotification,
    events: wsEvents,
  } = useNotificationSocket(USER_ID);

  const [pickerMode, setPickerMode] = useState<PickerMode>("idle");
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

  const [localEvents, setLocalEvents] = useState<
    { id: string; title: string; latitude: number; longitude: number; severity: string }[]
  >([]);

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
        }).catch(() => {});
      }
    }, 1500);
    return () => clearInterval(uploadTimer);
  }, [geolocation.latitude, geolocation.longitude]);

  // 按下「發布事件」按鈕 → 進入選擇模式
  const handleFabClick = useCallback(() => {
    setPickerMode("choosing");
    setFormError(null);
  }, []);

  // 選擇「使用目前位置」
  const handleUseCurrentLocation = useCallback(() => {
    if (geolocation.latitude !== null && geolocation.longitude !== null) {
      setPendingLocation({ latitude: geolocation.latitude, longitude: geolocation.longitude });
      setShowForm(true);
      setPickerMode("idle");
    } else {
      setFormError("無法取得目前位置，請確認 GPS 是否已開啟。");
      setPickerMode("idle");
    }
  }, [geolocation.latitude, geolocation.longitude]);

  // 選擇「從地圖選擇」→ 進入地圖選點模式
  const handlePickFromMap = useCallback(() => {
    setPickerMode("picking");
  }, []);

  // 地圖點擊：只有在 picking 模式下才觸發
  const handleMapClick = useCallback(
    (lat: number, lng: number) => {
      if (pickerMode !== "picking") return;
      setPendingLocation({ latitude: lat, longitude: lng });
      setShowForm(true);
      setPickerMode("idle");
    },
    [pickerMode],
  );

  const handleFormSubmit = useCallback(
    async (event: EventCreate) => {
      setSubmitting(true);
      setFormError(null);
      try {
        const result = await createEvent(event);
        setStatusMsg(
          `事件已發布！已推送給 ${result.delivered_count} 位附近使用者。`,
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
        setFormError("事件發布失敗。請確認後端服務是否運行中。");
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
    setPickerMode("idle");
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
    <div className={`app-container ${pickerMode === "picking" ? "picking-mode" : ""}`}>
      {/* 狀態列 */}
      <div className="status-bar">
        <span className={`connection-dot ${connected ? "connected" : "disconnected"}`} />
        <span>{connected ? "即時連線中" : "已斷線"}</span>
        {geolocation.error && (
          <span className="geo-warning">GPS：{geolocation.error}</span>
        )}
      </div>

      {/* 地圖 */}
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

      {/* 浮動發布按鈕 */}
      {pickerMode === "idle" && !showForm && (
        <button className="fab" onClick={handleFabClick}>
          ＋
        </button>
      )}

      {/* 選擇位置面板 */}
      {pickerMode === "choosing" && (
        <div className="picker-panel-overlay" onClick={() => setPickerMode("idle")}>
          <div className="picker-panel" onClick={(e) => e.stopPropagation()}>
            <h4>選擇事件位置</h4>
            <button className="picker-option" onClick={handleUseCurrentLocation}>
              <span className="picker-icon">📍</span>
              <div>
                <strong>使用目前位置</strong>
                <p>以你的 GPS 座標作為事件地點</p>
              </div>
            </button>
            <button className="picker-option" onClick={handlePickFromMap}>
              <span className="picker-icon">🗺️</span>
              <div>
                <strong>從地圖選擇</strong>
                <p>在地圖上點擊選擇位置</p>
              </div>
            </button>
            <button className="picker-cancel" onClick={() => setPickerMode("idle")}>
              取消
            </button>
          </div>
        </div>
      )}

      {/* 地圖選點提示 */}
      {pickerMode === "picking" && (
        <div className="picking-hint">
          📍 請在地圖上點擊選擇事件位置
          <button onClick={() => setPickerMode("idle")}>✕</button>
        </div>
      )}

      {/* 事件表單 */}
      {showForm && pendingLocation && (
        <EventForm
          latitude={pendingLocation.latitude}
          longitude={pendingLocation.longitude}
          onSubmit={handleFormSubmit}
          submitting={submitting}
          onCancel={handleFormCancel}
        />
      )}

      {/* 表單錯誤 */}
      {formError && (
        <div className="form-error-banner">
          <span>{formError}</span>
          <button onClick={() => setFormError(null)}>關閉</button>
        </div>
      )}

      {/* 通知橫幅 */}
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

      {/* 狀態訊息 */}
      {statusMsg && (
        <div className="toast" onClick={() => setStatusMsg(null)}>
          {statusMsg}
        </div>
      )}
    </div>
  );
}
