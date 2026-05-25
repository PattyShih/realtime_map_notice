import type { LocationUpdate, LocationNearbyResponse } from "../types/api";

const BASE_URL = import.meta.env.VITE_LOCATION_SERVICE_URL ?? "http://localhost:8001";

export async function updateLocation(payload: LocationUpdate): Promise<void> {
  const res = await fetch(`${BASE_URL}/locations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    throw new Error(`Location update failed: ${res.status}`);
  }
}

export async function getNearbyUsers(
  latitude: number,
  longitude: number,
  radiusMeters = 500,
): Promise<LocationNearbyResponse> {
  const params = new URLSearchParams({
    latitude: String(latitude),
    longitude: String(longitude),
    radius_meters: String(radiusMeters),
  });
  const res = await fetch(`${BASE_URL}/locations/nearby?${params}`);
  if (!res.ok) {
    throw new Error(`Nearby query failed: ${res.status}`);
  }
  return res.json();
}