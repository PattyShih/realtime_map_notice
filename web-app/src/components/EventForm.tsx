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

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!title.trim() || !message.trim()) return;
    onSubmit({
      title: title.trim(),
      message: message.trim(),
      latitude,
      longitude,
      severity,
      radius_meters: 500,
    });
    setTitle("");
    setMessage("");
    setSeverity("info");
  };

  return (
    <div className="event-form-overlay">
      <form className="event-form" onSubmit={handleSubmit}>
        <h3>Post an Event</h3>
        <p className="form-location">
          at {latitude.toFixed(5)}, {longitude.toFixed(5)}
        </p>

        <label>
          Title
          <input
            type="text"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="e.g. Library 3F has seats"
            required
            maxLength={80}
          />
        </label>

        <label>
          Message
          <textarea
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            placeholder="Brief description..."
            required
            maxLength={200}
            rows={3}
          />
        </label>

        <label>
          Severity
          <select
            value={severity}
            onChange={(e) =>
              setSeverity(e.target.value as "info" | "urgent")
            }
          >
            <option value="info">Info — general notice</option>
            <option value="urgent">Urgent — needs attention</option>
          </select>
        </label>

        <div className="form-actions">
          <button type="submit" disabled={submitting}>
            {submitting ? "Posting..." : "Post Event"}
          </button>
          <button type="button" onClick={onCancel} className="cancel-btn">
            Cancel
          </button>
        </div>
      </form>
    </div>
  );
}