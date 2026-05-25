import { useState, useEffect, useRef } from "react";

export interface GeolocationState {
  latitude: number | null;
  longitude: number | null;
  accuracy: number | null;
  error: string | null;
  loading: boolean;
}

const FALLBACK_COORDS = { latitude: 25.0173, longitude: 121.5397 }; // NTU center

export function useGeolocation() {
  const [state, setState] = useState<GeolocationState>({
    latitude: null,
    longitude: null,
    accuracy: null,
    error: null,
    loading: true,
  });
  const watchId = useRef<number | null>(null);

  useEffect(() => {
    if (!navigator.geolocation) {
      setState((s) => ({
        ...s,
        error: "Geolocation not supported by this browser",
        loading: false,
        ...FALLBACK_COORDS,
      }));
      return;
    }

    watchId.current = navigator.geolocation.watchPosition(
      (position) => {
        setState({
          latitude: position.coords.latitude,
          longitude: position.coords.longitude,
          accuracy: position.coords.accuracy,
          error: null,
          loading: false,
        });
      },
      (err) => {
        setState((s) => ({
          ...s,
          error: err.message,
          loading: false,
          ...(s.latitude === null ? FALLBACK_COORDS : {}),
        }));
      },
      { enableHighAccuracy: true, maximumAge: 2000, timeout: 10000 },
    );

    return () => {
      if (watchId.current !== null) {
        navigator.geolocation.clearWatch(watchId.current);
      }
    };
  }, []);

  return state;
}