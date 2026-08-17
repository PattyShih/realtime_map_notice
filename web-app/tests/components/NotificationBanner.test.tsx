import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import NotificationBanner from "../../src/components/NotificationBanner";
import type { EventNotification } from "../../src/types/api";

const urgentNotification: EventNotification = {
  event_id: "evt-1",
  title: "Road blocked",
  message: "Path near library is blocked",
  latitude: 25.0173,
  longitude: 121.5397,
  severity: "urgent",
  distance_meters: 123.4,
};

describe("NotificationBanner", () => {
  it("renders notification content and rounded distance", () => {
    render(
      <NotificationBanner
        notification={urgentNotification}
        onView={vi.fn()}
        onDismiss={vi.fn()}
      />,
    );

    expect(screen.getByText("URGENT")).toBeInTheDocument();
    expect(screen.getByText("Road blocked")).toBeInTheDocument();
    expect(screen.getByText("Path near library is blocked")).toBeInTheDocument();
    expect(screen.getByText("123m from you")).toBeInTheDocument();
  });

  it("calls view with event coordinates", async () => {
    const user = userEvent.setup();
    const onView = vi.fn();

    render(
      <NotificationBanner
        notification={urgentNotification}
        onView={onView}
        onDismiss={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "View" }));

    expect(onView).toHaveBeenCalledWith(25.0173, 121.5397);
  });

  it("calls dismiss handler", async () => {
    const user = userEvent.setup();
    const onDismiss = vi.fn();

    render(
      <NotificationBanner
        notification={urgentNotification}
        onView={vi.fn()}
        onDismiss={onDismiss}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
