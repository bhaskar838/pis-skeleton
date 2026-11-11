import type { Me, Membership } from "@dcs/api-client";
import { describe, expect, it, vi } from "vitest";

import messages from "@/messages/en.json";

import { ABSOLUTE_SECONDS, refreshAccessToken, sessionDecision } from "./auth-policy";
import { t } from "./i18n";
import { isActive, NAV, PAGE_PERMISSIONS, visibleNav } from "./nav";
import { assignableRoles, can, pickMembership, regionLabel } from "./org";
import { outcomeOf, problemMessage, toProblem } from "./problem";

// Permission sets as returned by GET /v1/me (mirrors packages/py/dcs_authz/policies.yaml).
const PERMS: Record<string, string[]> = {
  owner: ["org:read", "org:write", "members:read", "members:invite", "members:manage", "security:read", "audit:read",
    "notifications:read", "flags:read", "billing:read", "sources:read", "studio:read", "tools:read", "insights:read"],
  analyst: ["org:read", "notifications:read", "flags:read", "studio:read", "mapping:read", "pipeline:read", "tools:read",
    "tools:run", "insights:read", "actions:approve_basic"],
  viewer: ["org:read", "notifications:read", "flags:read", "insights:read"],
  billing: ["org:read", "notifications:read", "flags:read", "billing:read", "billing:write"],
};

function perms(role: string): string[] {
  return PERMS[role] ?? [];
}

function ids(items: ReturnType<typeof visibleNav>): string[] {
  return items.flatMap((i) => [i.id, ...(i.children ?? []).map((c) => c.id)]);
}

describe("visibleNav", () => {
  it("owner sees every section", () => {
    expect(ids(visibleNav(perms("owner")))).toEqual([
      "home", "sources", "studio", "toolkit", "insights", "billing", "settings",
      "settings-org", "settings-team", "settings-security", "settings-audit", "settings-notifications",
    ]);
  });

  it("analyst sees a limited nav (no sources, billing, team, audit)", () => {
    expect(ids(visibleNav(perms("analyst")))).toEqual([
      "home", "studio", "toolkit", "insights", "settings", "settings-org", "settings-notifications",
    ]);
  });

  it("viewer sees insights only plus personal settings", () => {
    expect(ids(visibleNav(perms("viewer")))).toEqual(["home", "insights", "settings", "settings-org", "settings-notifications"]);
  });

  it("billing role sees billing", () => {
    expect(ids(visibleNav(perms("billing")))).toContain("billing");
  });

  it("drops parents without visible children and nothing without permissions", () => {
    expect(visibleNav([])).toEqual([]);
    const items = [{ id: "p", href: "/p", label: "nav.home" as const, permission: "a", children: [{ id: "c", href: "/c", label: "nav.home" as const, permission: "b" }] }];
    expect(visibleNav(["a"], items)).toEqual([]);
    expect(visibleNav(["a", "b"], items)[0]?.href).toBe("/c");
  });

  it("every built page requires the same permission as its nav entry", () => {
    const all = NAV.flatMap((i) => [i, ...(i.children ?? [])]);
    for (const [path, perm] of Object.entries(PAGE_PERMISSIONS)) {
      const entry = all.find((i) => i.href === path && !i.children);
      if (entry) expect(entry.permission).toBe(perm);
    }
  });

  it("every nav label has an English string", () => {
    for (const item of NAV.flatMap((i) => [i, ...(i.children ?? [])])) {
      expect(messages[item.label]).toBeTruthy();
      expect(t(item.label)).not.toBe(item.label);
    }
    expect(t("missing.key")).toBe("missing.key");
  });

  it("isActive", () => {
    expect(isActive("/", "/")).toBe(true);
    expect(isActive("/", "/settings/org")).toBe(false);
    expect(isActive("/settings/org", "/settings/org")).toBe(true);
    expect(isActive("/settings", "/settings/team")).toBe(true);
    expect(isActive("/settings", "/settingsx")).toBe(false);
  });
});

describe("org helpers", () => {
  const m = (org: string, role: Membership["role"], perms: string[] = []): Membership =>
    ({ org_id: org, role, permissions: perms }) as unknown as Membership;
  const me = { memberships: [m("a", "owner"), m("b", "viewer")] } as unknown as Me;

  it("picks the selected org only when the user is still a member", () => {
    expect(pickMembership(me, "b")?.org_id).toBe("b");
    expect(pickMembership(me, "zzz")?.org_id).toBe("a");
    expect(pickMembership(me, undefined)?.org_id).toBe("a");
    expect(pickMembership({ memberships: [] } as unknown as Me, "a")).toBeUndefined();
  });

  it("can / assignableRoles / regionLabel", () => {
    expect(can(m("a", "owner", ["x"]), "x")).toBe(true);
    expect(can(undefined, "x")).toBe(false);
    expect(assignableRoles("owner")).toContain("owner");
    expect(assignableRoles("admin")).not.toContain("owner");
    expect(assignableRoles("analyst")).toEqual([]);
    expect(regionLabel("ap-south-1")).toMatch(/India/);
    expect(regionLabel("eu-west-2")).toMatch(/London/);
    expect(regionLabel("us-east-1")).toMatch(/Virginia/);
    expect(regionLabel("xx-new-9")).toBe("xx-new-9");
  });
});

describe("problem mapping", () => {
  const fail = (status: number, slug = "x") => ({ ok: false as const, status, problem: { type: `https://errors.dcs-pis.app/${slug}`, title: "t", status } });

  it("maps API failures to page states", () => {
    expect(outcomeOf({ ok: true, status: 200, data: 1 })).toBe("ok");
    expect(outcomeOf(fail(401))).toBe("unauthenticated");
    expect(outcomeOf(fail(403, "mfa-required"))).toBe("mfa");
    expect(outcomeOf(fail(403))).toBe("forbidden");
    expect(outcomeOf(fail(404))).toBe("not-found");
    expect(outcomeOf(fail(409, "tenant-not-ready"))).toBe("not-ready");
    expect(outcomeOf(fail(500))).toBe("error");
  });

  it("builds readable messages", () => {
    expect(problemMessage({ type: "x", title: "Bad", status: 422, errors: [{ loc: ["body", "email"], msg: "invalid", type: "v" }] }))
      .toBe("email: invalid");
    expect(problemMessage({ type: "x", title: "Bad", status: 400, detail: "Nope" })).toBe("Nope");
    expect(problemMessage({ type: "x", title: "Bad", status: 400 })).toBe("Bad");
    expect(toProblem(502, "<html>").title).toBe("Server error");
    expect(toProblem(400, null).title).toBe("Request failed");
    expect(toProblem(403, { type: "t", status: 403, title: "F" }).title).toBe("F");
  });
});

describe("session policy", () => {
  const now = 1_800_000_000;

  it("decides between fresh, refresh, broken and expired", () => {
    expect(sessionDecision({ auth_time: now - ABSOLUTE_SECONDS - 1 }, now)).toBe("expired");
    expect(sessionDecision({ auth_time: now, expires_at: now + 120 }, now)).toBe("fresh");
    expect(sessionDecision({ auth_time: now, expires_at: now + 30, refresh_token: "r" }, now)).toBe("refresh");
    expect(sessionDecision({ auth_time: now, expires_at: now + 30 }, now)).toBe("broken");
  });

  it("refreshes tokens and flags failures", async () => {
    const ok = vi.fn(async () => new Response(JSON.stringify({ access_token: "new", expires_in: 300, refresh_token: "r2" }), { status: 200 }));
    const refreshed = await refreshAccessToken({ refresh_token: "r1", access_token: "old" }, ok as unknown as typeof fetch);
    expect(refreshed.access_token).toBe("new");
    expect(refreshed.refresh_token).toBe("r2");
    expect(refreshed.error).toBeUndefined();

    const denied = vi.fn(async () => new Response(JSON.stringify({ error: "invalid_grant" }), { status: 400 }));
    expect((await refreshAccessToken({ refresh_token: "r1" }, denied as unknown as typeof fetch)).error).toBe("RefreshTokenError");

    const down = vi.fn(async () => {
      throw new Error("network");
    });
    expect((await refreshAccessToken({ refresh_token: "r1" }, down as unknown as typeof fetch)).error).toBe("RefreshTokenError");
  });
});
