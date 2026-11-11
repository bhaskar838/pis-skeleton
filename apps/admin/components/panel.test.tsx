import type { Schemas } from "@dcs/api-client";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { Setting } from "@/lib/panel";

vi.mock("next/navigation", () => ({ usePathname: () => "/body", redirect: vi.fn() }));
vi.mock("@/app/(console)/panel-actions", () => ({
  saveSetting: vi.fn(),
  saveSecret: vi.fn(),
  clearSecret: vi.fn(),
  resetSetting: vi.fn(),
}));
const loadPanel = vi.fn();
vi.mock("@/lib/panel-server", () => ({ loadPanel }));

const { SettingsSection } = await import("./settings-section");
const { SectionPage } = await import("./section-page");

function setting(over: Partial<Setting>): Setting {
  return {
    key: "body.product_name",
    section: "body",
    label: "Product name",
    help: "Shown everywhere.",
    type: "string",
    value: "DCS-PIS",
    default: "DCS-PIS",
    source: "default",
    is_set: true,
    version: 0,
    updated_by: null,
    updated_at: null,
    min: null,
    max: null,
    choices: [],
    optional: false,
    public: true,
    used_from: "P0.5",
    write_permission: "platform:config:write",
    ...over,
  };
}

const SECTION: Schemas["ConfigSectionOut"] = {
  id: "body",
  name: "Body",
  description: "What customers see",
  settings: [
    setting({ source: "panel", version: 2, value: "Kesari" }),
    setting({ key: "chassis.max_orgs_per_user", label: "Organisations per user", type: "int", value: 3, default: 3, min: 1, max: 100, public: false }),
    setting({ key: "electricals.smtp_starttls", label: "Use STARTTLS", type: "bool", value: true, default: false, public: false }),
    setting({ key: "trims.concierge_onboarding", label: "Concierge onboarding", type: "enum", value: "free", default: "free", choices: ["free", "paid"], used_from: "P6", public: false }),
    setting({ key: "trims.concierge_onboarding_price", label: "Concierge price", type: "money", value: { INR: "4999.00" }, default: {}, public: false }),
    setting({ key: "body.support_email", label: "Support e-mail", type: "email", value: "help@example.com" }),
    setting({
      key: "electricals.smtp_password",
      label: "SMTP password",
      type: "secret",
      value: null,
      default: null,
      source: "panel",
      is_set: true,
      version: 2,
      updated_by: "staff:alice",
      updated_at: "2026-11-11T10:00:00Z",
      write_permission: "platform:secrets:write",
      public: false,
    }),
  ],
};

const ALL = new Set(["platform:config:write", "platform:secrets:write"]);

describe("SettingsSection", () => {
  it("renders an editor per type with source, default, history and reset", () => {
    render(<SettingsSection section={SECTION} path="/body" permissions={ALL} />);
    expect(screen.getByLabelText("Product name value")).toHaveValue("Kesari");
    expect(screen.getAllByText("Panel · v2")).toHaveLength(2);
    expect(screen.getByLabelText("Organisations per user value")).toHaveValue(3);
    expect(screen.getByText("Range: 1 – 100")).toBeInTheDocument();
    expect(screen.getByLabelText("Use STARTTLS value")).toBeChecked();
    expect(screen.getByLabelText("Concierge onboarding value")).toHaveValue("free");
    expect(screen.getByText("Used from P6")).toBeInTheDocument();
    expect(screen.getByLabelText("Concierge price INR")).toHaveValue("4999.00");
    expect(screen.getByLabelText("Support e-mail value")).toHaveAttribute("type", "email");
    expect(screen.getAllByRole("link", { name: "History" })[0]).toHaveAttribute("href", "/config/body.product_name");
    expect(screen.getByRole("button", { name: "Reset to default" })).toBeInTheDocument();
    expect(screen.getByText(/v2 · by staff:alice/)).toBeInTheDocument();
    expect(screen.getByLabelText("SMTP password new value")).toHaveAttribute("type", "password");
    expect(screen.getByRole("button", { name: "Rotate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Clear" })).toBeInTheDocument();
    expect(screen.getAllByText("Shown to customers").length).toBeGreaterThan(0);
  });

  it("is read-only without write permissions and shows unset secrets", () => {
    const unset = { ...SECTION, settings: [setting({ ...SECTION.settings[6], is_set: false, version: 0, source: "default", updated_by: null, updated_at: null })] };
    render(<SettingsSection section={unset} path="/electricals" permissions={new Set()} />);
    expect(screen.getByText("Not set")).toBeInTheDocument();
    expect(screen.getByText("Only staff admins can set secrets.")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("disables inputs for read-only staff", () => {
    render(<SettingsSection section={{ ...SECTION, settings: SECTION.settings.slice(0, 1) }} path="/body" permissions={new Set()} />);
    expect(screen.getByLabelText("Product name value")).toBeDisabled();
    expect(screen.queryByRole("button", { name: "Save" })).not.toBeInTheDocument();
  });

  it("shows an empty state when a part has no settings yet", () => {
    render(<SettingsSection section={{ ...SECTION, settings: [] }} path="/wheels" permissions={ALL} />);
    expect(screen.getByText("Nothing to adjust here yet")).toBeInTheDocument();
  });
});

describe("SectionPage", () => {
  it("lists the section and what later phases fit to it", async () => {
    loadPanel.mockResolvedValueOnce({
      ok: true,
      config: { sections: [{ id: "wheels", name: "Wheels", description: "Floor 1: how data gets in", settings: [] }], deployment: [] },
      permissions: ALL,
    });
    render(await SectionPage({ sectionId: "wheels", fittings: [{ label: "Upload limits", phase: "P1", detail: "file size" }] }));
    expect(screen.getByRole("heading", { name: "Wheels" })).toBeInTheDocument();
    expect(screen.getByText("Fitted in later phases")).toBeInTheDocument();
    expect(screen.getByText("Upload limits")).toBeInTheDocument();
  });

  it("handles unknown sections and API failures", async () => {
    loadPanel.mockResolvedValueOnce({ ok: true, config: { sections: [], deployment: [] }, permissions: ALL });
    render(await SectionPage({ sectionId: "nope" }));
    expect(screen.getByText("Not found")).toBeInTheDocument();
    loadPanel.mockResolvedValueOnce({ ok: false, result: { ok: false, status: 403, problem: { type: "about:blank", title: "Forbidden", status: 403 } } });
    render(await SectionPage({ sectionId: "body" }));
    expect(screen.getByText(/staff role doesn't include/)).toBeInTheDocument();
  });
});
