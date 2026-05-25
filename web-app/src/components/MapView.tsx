import { useEffect } from "react";
import {
  MapContainer,
  TileLayer,
  Marker,
  Popup,
  useMap,
  useMapEvents,
} from "react-leaflet";
import L from "leaflet";
import type { MapEvent } from "../types/api";
import "leaflet/dist/leaflet.css";

// Fix default marker icon paths (Leaflet + bundler issue)
import iconUrl from "leaflet/dist/images/marker-icon.png";
import iconRetinaUrl from "leaflet/dist/images/marker-icon-2x.png";
import shadowUrl from "leaflet/dist/images/marker-shadow.png";

delete (L.Icon.Default.prototype as any)._getIconUrl;
L.Icon.Default.mergeOptions({ iconUrl, iconRetinaUrl, shadowUrl });

const urgentIcon = new L.Icon({
  iconUrl,
  iconRetinaUrl,
  shadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  className: "urgent-marker",
});

const infoIcon = new L.Icon({
  iconUrl,
  iconRetinaUrl,
  shadowUrl,
  iconSize: [25, 41],
  iconAnchor: [12, 41],
  popupAnchor: [1, -34],
  className: "info-marker",
});

interface MapViewProps {
  userLocation: { latitude: number; longitude: number } | null;
  events: MapEvent[];
  onMapClick: (lat: number, lng: number) => void;
  pendingLocation: { latitude: number; longitude: number } | null;
}

function MapController({
  userLocation,
}: {
  userLocation: { latitude: number; longitude: number } | null;
}) {
  const map = useMap();

  useEffect(() => {
    if (userLocation) {
      map.setView(
        [userLocation.latitude, userLocation.longitude],
        map.getZoom(),
      );
    }
  }, [userLocation, map]);

  return null;
}

function ClickHandler({
  onClick,
}: {
  onClick: (lat: number, lng: number) => void;
}) {
  useMapEvents({
    click(e) {
      onClick(e.latlng.lat, e.latlng.lng);
    },
  });
  return null;
}

export default function MapView({
  userLocation,
  events,
  onMapClick,
  pendingLocation,
}: MapViewProps) {
  const defaultCenter: [number, number] = userLocation
    ? [userLocation.latitude, userLocation.longitude]
    : [25.0173, 121.5397];

  return (
    <MapContainer
      center={defaultCenter}
      zoom={16}
      style={{ width: "100%", height: "100%" }}
    >
      <TileLayer
        attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
        url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
      />
      <MapController userLocation={userLocation} />
      <ClickHandler onClick={onMapClick} />

      {/* User location marker */}
      {userLocation && (
        <Marker position={[userLocation.latitude, userLocation.longitude]}>
          <Popup>You are here</Popup>
        </Marker>
      )}

      {/* Pending event location marker */}
      {pendingLocation && (
        <Marker position={[pendingLocation.latitude, pendingLocation.longitude]} />
      )}

      {/* Event markers */}
      {events.map((event) => (
        <Marker
          key={event.id}
          position={[event.latitude, event.longitude]}
          icon={event.severity === "urgent" ? urgentIcon : infoIcon}
        >
          <Popup>
            <strong>{event.title}</strong>
            <p>{event.message}</p>
            {event.distance_meters != null && (
              <small>{Math.round(event.distance_meters)}m away</small>
            )}
          </Popup>
        </Marker>
      ))}
    </MapContainer>
  );
}