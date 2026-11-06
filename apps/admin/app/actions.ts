"use server";

import { problemMessage } from "@dcs/api-client";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";
import { z } from "zod";

import { signOut } from "@/auth";
import { call, getAccessToken } from "@/lib/api";

export interface ActionState {
  ok?: boolean;
  error?: string;
  message?: string;
}

export async function staffSignOut(): Promise<void> {
  const session = await getAccessToken();
  const issuer = process.env.AUTH_KEYCLOAK_ISSUER ?? "";
  const back = encodeURIComponent(`${process.env.AUTH_URL ?? "http://localhost:3001"}/auth/sign-in`);
  const hint = session?.idToken ? `&id_token_hint=${encodeURIComponent(session.idToken)}` : "";
  await signOut({ redirectTo: `${issuer}/protocol/openid-connect/logout?post_logout_redirect_uri=${back}${hint}&client_id=${process.env.AUTH_KEYCLOAK_ID ?? ""}` });
}

const deprovisionSchema = z.object({
  org_id: z.string().uuid(),
  confirm_slug: z.string().min(1, "Type the tenant slug to confirm"),
  reason: z.string().trim().min(3, "Give a reason (min 3 characters)").max(500),
  pending_days: z.coerce.number().int().min(7).max(30),
});

export async function deprovisionTenant(_: ActionState | null, form: FormData): Promise<ActionState> {
  const parsed = deprovisionSchema.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues.map((i) => i.message).join("; ") };
  const { org_id, ...body } = parsed.data;
  const result = await call(`/v1/admin/tenants/${org_id}/deprovision`, { method: "POST", body });
  if (!result.ok) return { error: problemMessage(result.problem) };
  revalidatePath(`/tenants/${org_id}`);
  return { ok: true, message: "Deprovisioning started. Every step is recorded in the tenant's audit log." };
}

export async function retryProvisioning(form: FormData): Promise<void> {
  const id = z.string().uuid().parse(form.get("org_id"));
  await call(`/v1/admin/tenants/${id}/retry-provisioning`, { method: "POST" });
  revalidatePath(`/tenants/${id}`);
}

export async function runVerification(): Promise<void> {
  await call("/v1/admin/audit/verify", { method: "POST" });
  revalidatePath("/security");
}

const flagSchema = z.object({
  key: z.string().regex(/^[a-z][a-z0-9_.-]{1,63}$/, "Lowercase key, e.g. system.maintenance"),
  scope: z.enum(["global", "plan", "org"]),
  scope_id: z.string().max(64).optional().default(""),
  value: z.string().min(1, "Value is required"),
});

export async function upsertFlag(_: ActionState | null, form: FormData): Promise<ActionState> {
  const parsed = flagSchema.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues.map((i) => i.message).join("; ") };
  let value: unknown;
  try {
    value = JSON.parse(parsed.data.value);
  } catch {
    return { error: "Value must be JSON, e.g. true, 10 or \"text\"." };
  }
  const result = await call("/v1/admin/flags", { method: "PUT", body: { ...parsed.data, value } });
  if (!result.ok) return { error: problemMessage(result.problem) };
  revalidatePath("/settings");
  return { ok: true, message: `Saved ${parsed.data.key}.` };
}

export async function deleteFlag(form: FormData): Promise<void> {
  const key = String(form.get("key"));
  const scope = String(form.get("scope"));
  const scopeId = String(form.get("scope_id") ?? "");
  await call(`/v1/admin/flags/${encodeURIComponent(key)}?scope=${scope}&scope_id=${encodeURIComponent(scopeId)}`, { method: "DELETE" });
  revalidatePath("/settings");
}

export async function setMaintenance(form: FormData): Promise<void> {
  const on = form.get("on") === "true";
  await call("/v1/admin/flags", { method: "PUT", body: { key: "system.maintenance", scope: "global", scope_id: "", value: on } });
  revalidatePath("/settings");
  redirect("/settings");
}
