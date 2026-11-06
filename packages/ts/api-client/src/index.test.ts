import { describe, expect, it, vi } from "vitest";

import { createControlClient, isProblem, problemSlug } from "./index";

describe("problem helpers", () => {
  it("extracts the slug", () => {
    expect(problemSlug({ type: "https://errors.dcs-pis.app/mfa-required" })).toBe("mfa-required");
    expect(problemSlug(undefined)).toBeUndefined();
    expect(problemSlug({ type: "" })).toBeUndefined();
  });

  it("recognises problem objects", () => {
    expect(isProblem({ type: "x", status: 403, title: "Forbidden" })).toBe(true);
    expect(isProblem({ status: 403 })).toBe(false);
    expect(isProblem(null)).toBe(false);
  });
});

describe("createControlClient", () => {
  it("sends bearer token and org header", async () => {
    const fetchMock = vi.fn(async (req: Request) => {
      expect(req.headers.get("Authorization")).toBe("Bearer tok");
      expect(req.headers.get("X-DCS-Org")).toBe("org-1");
      return new Response(JSON.stringify({ flags: {} }), { headers: { "content-type": "application/json" } });
    });
    const client = createControlClient({ baseUrl: "http://api.test", accessToken: "tok", orgId: "org-1",
      fetch: fetchMock as unknown as typeof fetch });
    const { data } = await client.GET("/v1/flags");
    expect(data).toEqual({ flags: {} });
    expect(fetchMock).toHaveBeenCalledOnce();
  });

  it("omits headers when not provided", async () => {
    const fetchMock = vi.fn(async (req: Request) => {
      expect(req.headers.get("Authorization")).toBeNull();
      expect(req.headers.get("X-DCS-Org")).toBeNull();
      return new Response("{}", { headers: { "content-type": "application/json" } });
    });
    const client = createControlClient({ baseUrl: "http://api.test", fetch: fetchMock as unknown as typeof fetch });
    await client.GET("/v1/invites/{token}", { params: { path: { token: "abc" } } });
  });
});
