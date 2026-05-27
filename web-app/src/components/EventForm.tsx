import { useState } from "react";
import type { EventCreate } from "../types/api";

interface EventFormProps {
  latitude: number;
  longitude: number;
  onSubmit: (event: EventCreate) => void;
  submitting: boolean;
  onCancel: () => void;
}

// 常用事件快選
const QUICK_EVENTS = [
  { title: "有空位", message: "這裡目前有空位", severity: "info" as const, icon: "🪑" },
  { title: "排隊人多", message: "排隊人潮較多，請留意等待時間", severity: "info" as const, icon: "👥" },
  { title: "人潮聚集", message: "此處人潮聚集中", severity: "info" as const, icon: "📍" },
  { title: "免費活動", message: "這裡有免費活動進行中", severity: "info" as const, icon: "🎉" },
  { title: "遺失物", message: "這裡有撿到遺失物", severity: "info" as const, icon: "🔍" },
  { title: "施工封路", message: "此處施工中，請改道", severity: "urgent" as const, icon: "🚧" },
  { title: "走失寵物", message: "有走失寵物在此處出沒", severity: "urgent" as const, icon: "🐾" },
  { title: "安全提醒", message: "此處有安全疑慮，請小心", severity: "urgent" as const, icon: "⚠️" },
];

// 有效期限選項
const EXPIRY_OPTIONS = [
  { label: "10 分鐘", value: 10 },
  { label: "30 分鐘", value: 30 },
  { label: "1 小時", value: 60 },
  { label: "2 小時", value: 120 },
  { label: "6 小時", value: 360 },
  { label: "12 小時", value: 720 },
];

export default function EventForm({
  latitude,
  longitude,
  onSubmit,
  submitting,
  onCancel,
}: EventFormProps) {
  const [title, setTitle] = useState("");
  const [message, setMessage] = useState("");
  const [severity, setSeverity] = useState<"info" | "urgent">("info");
  const [radiusMeters, setRadiusMeters] = useState(500);
  const [expiresIn, setExpiresIn] = useState(30);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim()) return;
    onSubmit({
      client_event_id: crypto.randomUUID(),
      title: title.trim(),
      message: message.trim(),
      latitude,
      longitude,
      severity,
      radius_meters: radiusMeters,
      expires_in: expiresIn,
    });
    setTitle("");
    setMessage("");
    setSeverity("info");
  };

  const handleQuickSelect = (qe: typeof QUICK_EVENTS[number]) => {
    setTitle(qe.title);
    setMessage(qe.message);
    setSeverity(qe.severity);
  };

  return (
    <div className="event-form-overlay">
      <form className="event-form" onSubmit={handleSubmit}>
        <h3>發布事件</h3>
        <p className="form-location">
          座標：{latitude.toFixed(5)}, {longitude.toFixed(5)}
        </p>

        {/* 常用事件快選 */}
        <div className="quick-events">
          <span className="quick-events-label">快速選擇</span>
          <div className="quick-events-grid">
            {QUICK_EVENTS.map((qe) => (
              <button
                key={qe.title}
                type="button"
                className={`quick-btn ${title === qe.title ? "active" : ""} ${qe.severity}`}
                onClick={() => handleQuickSelect(qe)}
              >
                <span className="quick-icon">{qe.icon}</span>
                <span className="quick-text">{qe.title}</span>
              </button>
            ))}
          </div>
        </div>

        <label>
          標題
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="例：圖書館 3 樓有空位"
            required
            maxLength={80}
          />
        </label>

        <label>
          描述
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="簡短描述..."
            required
            maxLength={200}
            rows={2}
          />
        </label>

        <div className="form-row">
          <label className="form-row-item">
            嚴重程度
            <select
              value={severity}
              onChange={(e) =>
                setSeverity(e.target.value as "info" | "urgent")
              }
            >
              <option value="info">一般</option>
              <option value="urgent">緊急</option>
            </select>
          </label>

          <label className="form-row-item">
            有效期限
            <select
              value={expiresIn}
              onChange={(e) => setExpiresIn(Number(e.target.value))}
            >
              {EXPIRY_OPTIONS.map((opt) => (
                <option key={opt.value} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </label>
        </div>

        <label>
          通知範圍：{radiusMeters} 公尺
          <div className="radius-slider-row">
            <span>100</span>
            <input
              type="range"
              min={100}
              max={2000}
              step={100}
              value={radiusMeters}
              onChange={(e) => setRadiusMeters(Number(e.target.value))}
              className="radius-slider"
            />
            <span>2000</span>
          </div>
        </label>

        <div className="form-actions">
          <button type="submit" disabled={submitting}>
            {submitting ? "發布中..." : "發布事件"}
          </button>
          <button type="button" onClick={onCancel} className="cancel-btn">
            取消
          </button>
        </div>
      </form>
    </div>
  );
}
