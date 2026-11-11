import { describe, expect, it } from "vitest";

import { ADMIN_NAV, ADMIN_NAV_GROUPS, isActive, visibleAdminNav } from "./nav";

describe("admin nav (car layout, ADR-0011)", () => {
  it("is organised by the parts of the car", () => {
    expect(ADMIN_NAV_GROUPS.map((g) => g.part)).toEqual([
      "Dashboard",
      "Cabin",
      "Chassis",
      "Body",
      "Electricals",
      "Trims & options",
      "Wheels",
      "Fuel lines",
      "Engine bay",
      "Switchgear",
      "Locks & keys",
    ]);
  });

  it("support staff see read-only parts but not switchgear", () => {
    const groups = visibleAdminNav(["platform:dashboard:read", "platform:tenants:read", "platform:audit:read", "platform:config:read"]);
    const labels = groups.flatMap((g) => g.items.map((i) => i.label));
    expect(labels).toContain("Tenants");
    expect(labels).toContain("Regions & limits");
    expect(labels).toContain("Audit & staff access");
    expect(labels).not.toContain("Feature flags");
    expect(groups.find((g) => g.part === "Switchgear")).toBeUndefined();
  });

  it("admins see everything; nobody sees anything without permissions", () => {
    const all = new Set(ADMIN_NAV.map((i) => i.permission));
    expect(visibleAdminNav(all).flatMap((g) => g.items)).toHaveLength(ADMIN_NAV.length);
    expect(visibleAdminNav([])).toEqual([]);
  });

  it("built pages are the Phase 0 + 0.5 set; the rest name their phase", () => {
    expect(ADMIN_NAV.filter((i) => !i.soon).map((i) => i.href)).toEqual([
      "/",
      "/tenants",
      "/chassis",
      "/body",
      "/electricals",
      "/trims",
      "/wheels",
      "/fuel-lines",
      "/engine-bay",
      "/settings",
      "/security",
    ]);
    for (const i of ADMIN_NAV.filter((n) => n.soon)) expect(i.soon).toMatch(/^P\d$/);
  });

  it("isActive", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/tenants")).toBe(false);
    expect(isActive("/tenants", "/tenants/abc")).toBe(true);
  });
});
