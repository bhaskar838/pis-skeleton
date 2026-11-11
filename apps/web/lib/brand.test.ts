import { describe, expect, it, vi } from "vitest";

const call = vi.fn();
vi.mock("./api", () => ({ call }));

const { FALLBACK_BRAND, getBrand, getSignupCountries } = await import("./brand");

describe("brand and sign-up countries from the control panel", () => {
  it("uses panel values without a token or org header", async () => {
    call.mockResolvedValueOnce({ ok: true, status: 200, data: { ...FALLBACK_BRAND, product_name: "Kesari" } });
    expect((await getBrand()).product_name).toBe("Kesari");
    expect(call).toHaveBeenLastCalledWith("/v1/public/brand", { auth: false, org: false });
    call.mockResolvedValueOnce({ ok: true, status: 200, data: [{ code: "IN", name: "India", region: "ap-south-1" }] });
    expect(await getSignupCountries()).toEqual([{ code: "IN", name: "India", region: "ap-south-1" }]);
  });

  it("falls back when the API is down", async () => {
    const down = { ok: false, status: 503, problem: { type: "about:blank", title: "Unavailable", status: 503 } };
    call.mockResolvedValueOnce(down);
    expect(await getBrand()).toEqual(FALLBACK_BRAND);
    call.mockResolvedValueOnce(down);
    expect(await getSignupCountries()).toEqual([]);
  });
});
