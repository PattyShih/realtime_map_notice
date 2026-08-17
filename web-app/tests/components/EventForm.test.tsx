import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import EventForm from "../../src/components/EventForm";

describe("EventForm", () => {
  it("submits trimmed event payload with selected severity", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <EventForm
        latitude={25.0173}
        longitude={121.5397}
        onSubmit={onSubmit}
        submitting={false}
        onCancel={vi.fn()}
      />,
    );

    await user.type(screen.getByLabelText("Title"), "  Library seats  ");
    await user.type(screen.getByLabelText("Message"), "  3F has seats  ");
    await user.selectOptions(screen.getByLabelText("Severity"), "urgent");
    await user.click(screen.getByRole("button", { name: "Post Event" }));

    expect(onSubmit).toHaveBeenCalledWith({
      title: "Library seats",
      message: "3F has seats",
      latitude: 25.0173,
      longitude: 121.5397,
      severity: "urgent",
      radius_meters: 500,
    });
  });

  it("does not submit blank required fields", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();

    render(
      <EventForm
        latitude={25.0173}
        longitude={121.5397}
        onSubmit={onSubmit}
        submitting={false}
        onCancel={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Post Event" }));

    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("calls cancel handler", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();

    render(
      <EventForm
        latitude={25.0173}
        longitude={121.5397}
        onSubmit={vi.fn()}
        submitting={false}
        onCancel={onCancel}
      />,
    );

    await user.click(screen.getByRole("button", { name: "Cancel" }));

    expect(onCancel).toHaveBeenCalledOnce();
  });
});
