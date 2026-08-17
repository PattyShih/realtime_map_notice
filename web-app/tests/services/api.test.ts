import { afterEach, describe, expect, it, vi } from "vitest";
import { createEvent } from "../../src/services/eventApi";
import { getNearbyUsers, updateLocation } from "../../src/services/locationApi";

describe("locationApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts location updates to Location Service", async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);

    await updateLocation({
      user_id: "u-1",
      latitude: 25.0173,
      longitude: 121.5397,
    });

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8001/locations",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          user_id: "u-1",
          latitude: 25.0173,
          longitude: 121.5397,
        }),
      },
    );
  });

  it("queries nearby users with radius", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(JSON.stringify({ users: ["u-1"] }), { status: 200 }),
      ),
    );

    const result = await getNearbyUsers(25.0173, 121.5397, 750);

    expect(result).toEqual({ users: ["u-1"] });
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8001/locations/nearby?latitude=25.0173&longitude=121.5397&radius_meters=750",
    );
  });

  it("throws when Location Service rejects request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 500 })),
    );

    await expect(
      updateLocation({ user_id: "u-1", latitude: 25.0173, longitude: 121.5397 }),
    ).rejects.toThrow("Location update failed: 500");
  });
});

describe("eventApi", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("posts event payload to Event Service", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            event_id: "evt-1",
            nearby_user_count: 2,
            delivered_count: 2,
            delivered_to: ["u-1", "u-2"],
            status: "created",
          }),
          { status: 200 },
        ),
      ),
    );

    const payload = {
      title: "Road blocked",
      message: "Path near library is blocked",
      latitude: 25.0173,
      longitude: 121.5397,
      severity: "urgent" as const,
      radius_meters: 500,
    };
    const result = await createEvent(payload);

    expect(result.delivered_count).toBe(2);
    expect(fetch).toHaveBeenCalledWith(
      "http://localhost:8002/events",
      {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      },
    );
  });

  it("throws when Event Service rejects request", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(null, { status: 422 })),
    );

    await expect(
      createEvent({
        title: "Bad",
        message: "Bad coordinate",
        latitude: 999,
        longitude: 121.5397,
        severity: "urgent",
        radius_meters: 500,
      }),
    ).rejects.toThrow("Event creation failed: 422");
  });
});
