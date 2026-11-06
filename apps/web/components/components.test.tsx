import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { visibleNav } from "@/lib/nav";

vi.mock("next/navigation", () => ({
  usePathname: () => "/settings/team",
  useRouter: () => ({ refresh: vi.fn() }),
  redirect: vi.fn(),
}));

const { Sidebar } = await import("./shell/sidebar");
const { FormMessage, SubmitButton } = await import("./submit-button");
const { NotificationBell, STEP_LABELS } = await import("./shell/live");
const { SystemPage } = await import("./system-page");
const { NavIcon } = await import("./shell/icons");

describe("Sidebar", () => {
  it("shows only permitted items and marks the current page", () => {
    render(<Sidebar items={visibleNav(["org:read", "members:read", "insights:read", "notifications:read"])} />);
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.queryByText("Data Sources")).not.toBeInTheDocument();
    expect(screen.getByText("Insights").closest("[aria-disabled]")).toHaveAttribute("aria-disabled", "true");
    expect(screen.getByRole("link", { name: "Team & roles" })).toHaveAttribute("aria-current", "page");
    expect(screen.queryByRole("link", { name: "Audit log" })).not.toBeInTheDocument();
  });
});

describe("forms", () => {
  it("renders submit button and messages", () => {
    render(
      <form>
        <SubmitButton>Save</SubmitButton>
      </form>,
    );
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    const { rerender } = render(<FormMessage state={{ error: "Nope" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Nope");
    rerender(<FormMessage state={{ ok: true, message: "Saved" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    rerender(<FormMessage state={null} />);
    expect(screen.queryByRole("status")).not.toBeInTheDocument();
  });
});

describe("NotificationBell", () => {
  it("shows the unread count accessibly", () => {
    render(<NotificationBell orgId="org-1" initialUnread={3} />);
    expect(screen.getByRole("link", { name: "Notifications (3 unread)" })).toHaveAttribute("href", "/notifications");
  });

  it("caps the badge and handles zero", () => {
    const { rerender } = render(<NotificationBell orgId="org-1" initialUnread={150} />);
    expect(screen.getByText("99+")).toBeInTheDocument();
    rerender(<NotificationBell orgId="org-1" initialUnread={0} />);
    expect(screen.getByRole("link", { name: "Notifications" })).toBeInTheDocument();
  });

  it("labels every provisioning step", () => {
    expect(Object.keys(STEP_LABELS)).toHaveLength(5);
  });
});

describe("SystemPage and icons", () => {
  it("renders code, title and default action", () => {
    render(<SystemPage code="404" title="Page not found" body="Gone" />);
    expect(screen.getByRole("heading", { name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go to home" })).toHaveAttribute("href", "/");
  });

  it("renders icons or nothing", () => {
    const { container } = render(<NavIcon name="home" />);
    expect(container.querySelector("svg")).not.toBeNull();
    const empty = render(<NavIcon />);
    expect(empty.container.innerHTML).toBe("");
  });
});
