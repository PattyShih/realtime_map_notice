import { useState } from "react";
import type { EventCreate } from "../types/api";

interface EventFormProps {
  latitude: number;
  longitude: number;
  onSubmit: (event: EventCreate) => void;
  submitting: boolean;
  onCancel: () => void;
}

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
    });
    setTitle("");
    setMessage("");
    setSeverity("info");
  };

  return (
    <div className="event-form-overlay">
      <form className="event-form" onSubmit={handleSubmit}>
        <h3>發布事件</h3>
        <p className="form-location">
          座標：{latitude.toFixed(5)}, {longitude.toFixed(5)}
        </p>

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
            rows={3}
          />
        </label>

        <label>
          嚴重程度
          <select
            value={severity}
            onChange={(e) =>
              setSeverity(e.target.value as "info" | "urgent")
            }
          >
            <option value="info">一般 — 一般通知</option>
            <option value="urgent">緊急 — 需要注意</option>
          </select>
        </label>

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
