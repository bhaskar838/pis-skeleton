"use server";

import { problemMessage } from "@dcs/api-client";
import { revalidatePath } from "next/cache";
import { z } from "zod";

import type { ActionState } from "@/app/actions";
import { call } from "@/lib/api";
import { formToValue, safePath, type Setting } from "@/lib/panel";

const keySchema = z.string().regex(/^[a-z_]+\.[a-z0-9_.]+$/);
const typeSchema = z.enum(["string", "int", "bool", "enum", "email", "url", "money", "secret"]);
const regionCode = z.string().regex(/^[a-z]{2}(-gov)?-[a-z]+-[0-9]$/, "Use an AWS region code, e.g. sa-east-1");

function done(path: string, message: string): ActionState {
  revalidatePath(path);
  return { ok: true, message };
}

export async function saveSetting(_: ActionState | null, form: FormData): Promise<ActionState> {
  const key = keySchema.safeParse(form.get("key"));
  const type = typeSchema.safeParse(form.get("type"));
  if (!key.success || !type.success) return { error: "Unknown setting." };
  const parsed = formToValue(type.data as Setting["type"], form);
  if (!parsed.ok) return { error: parsed.error };
  const r = await call<Setting>(`/v1/admin/config/${key.data}`, { method: "PUT", body: { value: parsed.value } });
  if (!r.ok) return { error: problemMessage(r.problem) };
  return done(safePath(form.get("path")), `Saved. Live everywhere within a few seconds (v${r.data.version}).`);
}

export async function resetSetting(form: FormData): Promise<void> {
  const key = keySchema.parse(form.get("key"));
  await call(`/v1/admin/config/${key}`, { method: "DELETE" });
  revalidatePath(safePath(form.get("path")));
}

export async function revertSetting(form: FormData): Promise<void> {
  const key = keySchema.parse(form.get("key"));
  const version = z.coerce.number().int().positive().parse(form.get("version"));
  await call(`/v1/admin/config/${key}/revert/${version}`, { method: "POST" });
  revalidatePath(`/config/${key}`);
}

export async function saveSecret(_: ActionState | null, form: FormData): Promise<ActionState> {
  const key = keySchema.safeParse(form.get("key"));
  const value = z.string().min(1, "Enter a value").max(4096).safeParse(form.get("value"));
  if (!key.success) return { error: "Unknown setting." };
  if (!value.success) return { error: value.error.issues[0]?.message ?? "Invalid value" };
  const r = await call<Setting>(`/v1/admin/secrets/${key.data}`, { method: "PUT", body: { value: value.data } });
  if (!r.ok) return { error: problemMessage(r.problem) };
  return done(safePath(form.get("path")), `Stored encrypted (v${r.data.version}). It cannot be shown again.`);
}

export async function clearSecret(form: FormData): Promise<void> {
  const key = keySchema.parse(form.get("key"));
  await call(`/v1/admin/secrets/${key}`, { method: "DELETE" });
  revalidatePath(safePath(form.get("path")));
}

export async function updateRegion(_: ActionState | null, form: FormData): Promise<ActionState> {
  const code = regionCode.safeParse(form.get("code"));
  const status = z.enum(["active", "planned", "disabled"]).safeParse(form.get("status"));
  if (!code.success || !status.success) return { error: "Invalid region change." };
  const r = await call(`/v1/admin/regions/${code.data}`, { method: "PATCH", body: { status: status.data } });
  if (!r.ok) return { error: problemMessage(r.problem) };
  return done("/chassis", `${code.data} is now ${status.data}.`);
}

const newRegion = z.object({
  code: regionCode,
  name: z.string().trim().min(1, "Give the region a name").max(60),
  sort: z.coerce.number().int().min(0).max(10000).default(100),
});

export async function createRegion(_: ActionState | null, form: FormData): Promise<ActionState> {
  const parsed = newRegion.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues.map((i) => i.message).join("; ") };
  const r = await call("/v1/admin/regions", { method: "POST", body: parsed.data });
  if (!r.ok) return { error: problemMessage(r.problem) };
  return done("/chassis", `Added ${parsed.data.code} as planned. Deploy its stack before activating it.`);
}

export async function updateCountry(_: ActionState | null, form: FormData): Promise<ActionState> {
  const code = z.string().regex(/^[A-Z]{2}$/).safeParse(form.get("code"));
  const region = regionCode.safeParse(form.get("region"));
  if (!code.success || !region.success) return { error: "Invalid country change." };
  const r = await call(`/v1/admin/countries/${code.data}`, {
    method: "PATCH",
    body: { region: region.data, signup_enabled: form.get("signup_enabled") === "on" },
  });
  if (!r.ok) return { error: problemMessage(r.problem) };
  return done("/chassis", `Saved ${code.data}.`);
}
