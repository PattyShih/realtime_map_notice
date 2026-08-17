import type { Comment, CommentCreate } from "../types/api";

const BASE = import.meta.env.VITE_EVENT_SERVICE_URL ?? "/api/event";

export async function fetchComments(eventId: string): Promise<Comment[]> {
  const res = await fetch(`${BASE}/events/${encodeURIComponent(eventId)}/comments`);
  if (!res.ok) throw new Error("Failed to fetch comments");
  return res.json();
}

export async function postComment(
  eventId: string,
  payload: CommentCreate,
): Promise<Comment> {
  const res = await fetch(`${BASE}/events/${encodeURIComponent(eventId)}/comments`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) throw new Error("Failed to post comment");
  return res.json();
}
