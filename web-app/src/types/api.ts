// Mirror of backend/shared/schemas.py

export interface LocationUpdate {
  user_id: string;
  latitude: number;
  longitude: number;
}

export interface LocationNearbyResponse {
  users: string[];
}

export interface EventCreate {
  client_event_id?: string | null;
  title: string;
  message: string;
  latitude: number;
  longitude: number;
  severity: "info" | "urgent";
  radius_meters: number;
  expires_in: number;
}

export interface EventCreateResponse {
  event_id: string;
  nearby_user_count: number;
  delivered_count: number;
  delivered_to: string[];
  status?: "created" | "duplicate";
}

export interface EventNotification {
  event_id: string;
  title: string;
  message: string;
  latitude: number;
  longitude: number;
  severity: "info" | "urgent";
  distance_meters: number | null;
}

export interface MapEvent {
  id: string;
  title: string;
  message: string;
  latitude: number;
  longitude: number;
  severity: "info" | "urgent";
  distance_meters: number | null;
  created_at: string;
}
