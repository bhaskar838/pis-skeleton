import { describe, expect, it } from "vitest";

import { ADMIN_NAV, isActive, visibleAdminNav } from "./nav";

describe("admin nav", () => {
  it("support staff do not see settings", () => {
    const labels = visibleAdminNav(["platform:dashboard:read", "platform:tenants:read", "platform:audit:read"]).map((i) => i.label);
    expect(labels).toContain("Tenants");
    expect(labels).toContain("Audit & staff access");
    expect(labels).not.toContain("Settings & flags");
  });

  it("admins see everything", () => {
    const all = new Set(ADMIN_NAV.map((i) => i.permission));
    expect(visibleAdminNav(all)).toHaveLength(ADMIN_NAV.length);
    expect(visibleAdminNav([])).toEqual([]);
  });

  it("built pages are exactly the Phase 0 set", () => {
    expect(ADMIN_NAV.filter((i) => !i.soon).map((i) => i.href)).toEqual(["/", "/tenants", "/security", "/settings"]);
  });

  it("isActive", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/tenants")).toBe(false);
    expect(isActive("/tenants", "/tenants/abc")).toBe(true);
  });
});
