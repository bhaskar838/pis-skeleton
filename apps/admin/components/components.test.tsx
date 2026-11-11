import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { visibleAdminNav } from "@/lib/nav";

vi.mock("next/navigation", () => ({ usePathname: () => "/tenants/abc", redirect: vi.fn() }));

const { AdminSidebar } = await import("./admin-sidebar");
const { FormMessage, SubmitButton } = await import("./form-bits");

describe("AdminSidebar", () => {
  it("marks the current section and disables future pages", () => {
    render(<AdminSidebar groups={visibleAdminNav(["platform:dashboard:read", "platform:tenants:read"])} />);
    expect(screen.getByRole("link", { name: "Tenants" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Instrument cluster" })).not.toHaveAttribute("aria-current");
    expect(screen.getByText("Connectors").closest("[aria-disabled]")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Cabin" })).toBeInTheDocument();
    expect(screen.queryByText("Feature flags")).not.toBeInTheDocument();
  });
});

describe("form bits", () => {
  it("renders submit button and messages", () => {
    render(
      <form>
        <SubmitButton>Go</SubmitButton>
      </form>,
    );
    expect(screen.getByRole("button", { name: "Go" })).toBeEnabled();
    const { rerender } = render(<FormMessage state={{ error: "Bad" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Bad");
    rerender(<FormMessage state={{ ok: true, message: "Done" }} />);
    expect(screen.getByRole("status")).toHaveTextContent("Done");
    rerender(<FormMessage state={null} />);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});
