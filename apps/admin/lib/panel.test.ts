import type { Schemas } from "@dcs/api-client";
import { describe, expect, it } from "vitest";

import { warningLights } from "./lights";
import { canWrite, displayValue, formToValue, safePath, type Setting, sourceLabel } from "./panel";

function form(entries: Record<string, string>): FormData {
  const f = new FormData();
  for (const [k, v] of Object.entries(entries)) f.set(k, v);
  return f;
}

const base: Setting = {
  key: "body.product_name",
  section: "body",
  label: "Product name",
  help: "",
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
};

describe("formToValue", () => {
  it("converts each setting type", () => {
    expect(formToValue("string", form({ value: "Kesari" }))).toEqual({ ok: true, value: "Kesari" });
    expect(formToValue("int", form({ value: " 7 " }))).toEqual({ ok: true, value: 7 });
    expect(formToValue("int", form({ value: "7.5" }))).toEqual({ ok: false, error: "Enter a whole number." });
    expect(formToValue("int", form({ value: "" })).ok).toBe(false);
    expect(formToValue("bool", form({ value: "on" }))).toEqual({ ok: true, value: true });
    expect(formToValue("bool", form({}))).toEqual({ ok: true, value: false });
    expect(formToValue("money", form({ amount_INR: "4999", amount_GBP: " ", amount_USD: "59.5" }))).toEqual({
      ok: true,
      value: { INR: "4999", USD: "59.5" },
    });
    expect(formToValue("secret", form({ value: "x" })).ok).toBe(false);
  });
});

describe("labels and guards", () => {
  it("describes where a value comes from", () => {
    expect(sourceLabel(base)).toEqual({ text: "Default", tone: "neutral" });
    expect(sourceLabel({ ...base, source: "panel", version: 3 })).toEqual({ text: "Panel · v3", tone: "primary" });
    expect(sourceLabel({ ...base, source: "environment" }).text).toBe("From deployment");
  });

  it("formats values", () => {
    expect(displayValue(true)).toBe("On");
    expect(displayValue("")).toBe("—");
    expect(displayValue({ INR: "4999.00" })).toBe("INR 4999.00");
    expect(displayValue({})).toBe("—");
    expect(displayValue(3)).toBe("3");
  });

  it("checks write permission and revalidation paths", () => {
    expect(canWrite(base, new Set(["platform:config:write"]))).toBe(true);
    expect(canWrite({ ...base, write_permission: "platform:secrets:write" }, new Set(["platform:config:write"]))).toBe(false);
    expect(safePath("/chassis")).toBe("/chassis");
    expect(safePath("https://evil.example")).toBe("/");
    expect(safePath(undefined)).toBe("/");
  });
});

describe("warning lights", () => {
  const dash: Schemas["DashboardOut"] = {
    tenants_by_status: { active: 2, failed: 1 },
    tenants_by_region: {},
    users: 3,
    audit_chains_failing: 0,
    last_verification_at: null,
  };

  it("lights up what needs attention", () => {
    const flags: Schemas["FlagRow"][] = [
      { key: "system.maintenance", scope: "global", scope_id: "", value: true, updated_by: null, updated_at: "2026-11-11T00:00:00Z" },
    ];
    const config: Schemas["ConfigOut"] = {
      sections: [{ id: "electricals", name: "", description: "", settings: [{ ...base, key: "electricals.smtp_host", value: "localhost" }] }],
      deployment: [],
    };
    const on = warningLights(dash, flags, config)
      .filter((l) => l.on)
      .map((l) => l.id);
    expect(on).toEqual(["maintenance", "provisioning", "email"]);
    expect(warningLights({ ...dash, tenants_by_status: {} }, [], null).every((l) => !l.on)).toBe(true);
  });
});
