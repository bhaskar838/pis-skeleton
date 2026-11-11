/** Pure helpers for the control panel (ADR-0011). No server-only imports, so they are unit-tested directly. */
import type { Schemas } from "@dcs/api-client";

export type Setting = Schemas["SettingOut"];
export type ConfigSection = Schemas["ConfigSectionOut"];

export const CURRENCIES = ["INR", "GBP", "EUR", "USD"] as const;

/** Section id → console route. */
export const SECTION_PATHS: Record<string, string> = {
  chassis: "/chassis",
  body: "/body",
  electricals: "/electricals",
  trims: "/trims",
  wheels: "/wheels",
  fuel_lines: "/fuel-lines",
  engine_bay: "/engine-bay",
};

export const PANEL_PATHS = new Set([...Object.values(SECTION_PATHS), "/settings", "/security"]);

export type Parsed = { ok: true; value: unknown } | { ok: false; error: string };

/** Turn a setting form into the JSON value the API expects. The API re-validates everything. */
export function formToValue(type: Setting["type"], form: FormData): Parsed {
  const raw = String(form.get("value") ?? "");
  switch (type) {
    case "int": {
      const n = Number(raw.trim());
      if (raw.trim() === "" || !Number.isInteger(n)) return { ok: false, error: "Enter a whole number." };
      return { ok: true, value: n };
    }
    case "bool":
      return { ok: true, value: raw === "on" || raw === "true" };
    case "money": {
      const out: Record<string, string> = {};
      for (const c of CURRENCIES) {
        const v = String(form.get(`amount_${c}`) ?? "").trim();
        if (v) out[c] = v;
      }
      return { ok: true, value: out };
    }
    case "secret":
      return { ok: false, error: "Secrets are saved with the secret form." };
    default:
      return { ok: true, value: raw };
  }
}

export function sourceLabel(s: Setting): { text: string; tone: "primary" | "neutral" | "warning" } {
  if (s.source === "panel") return { text: `Panel · v${s.version}`, tone: "primary" };
  if (s.source === "environment") return { text: "From deployment", tone: "warning" };
  return { text: "Default", tone: "neutral" };
}

export function displayValue(value: unknown): string {
  if (value === null || value === undefined || value === "") return "—";
  if (typeof value === "boolean") return value ? "On" : "Off";
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>);
    return entries.length ? entries.map(([k, v]) => `${k} ${String(v)}`).join(" · ") : "—";
  }
  return String(value);
}

export function canWrite(setting: Setting, permissions: ReadonlySet<string>): boolean {
  return permissions.has(setting.write_permission);
}

export function safePath(path: unknown): string {
  return typeof path === "string" && PANEL_PATHS.has(path) ? path : "/";
}
