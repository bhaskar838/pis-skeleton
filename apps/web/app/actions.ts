"use server";

import { revalidatePath } from "next/cache";
import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import { signOut } from "@/auth";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { problemMessage } from "@/lib/problem";
import { getAccessToken, ORG_COOKIE } from "@/lib/session";

export interface ActionState {
  ok?: boolean;
  error?: string;
  message?: string;
}

const COOKIE_OPTS = { httpOnly: true, sameSite: "lax" as const, secure: process.env.AUTH_URL?.startsWith("https"), path: "/" };

export async function switchOrg(orgId: string): Promise<void> {
  const { me } = await requireContext();
  if (!me.memberships.some((m) => m.org_id === orgId)) return; // only orgs the user belongs to
  (await cookies()).set(ORG_COOKIE, orgId, { ...COOKIE_OPTS, maxAge: 60 * 60 * 24 * 365 });
  redirect("/");
}

export async function signOutAction(): Promise<void> {
  const session = await getAccessToken();
  const issuer = process.env.AUTH_KEYCLOAK_ISSUER ?? "";
  const back = encodeURIComponent(`${process.env.AUTH_URL ?? "http://localhost:3000"}/auth/sign-in?signed_out=1`);
  const hint = session?.idToken ? `&id_token_hint=${encodeURIComponent(session.idToken)}` : "";
  (await cookies()).delete(ORG_COOKIE);
  // End the Keycloak SSO session too, not only the app cookie.
  await signOut({ redirectTo: `${issuer}/protocol/openid-connect/logout?post_logout_redirect_uri=${back}${hint}&client_id=${process.env.AUTH_KEYCLOAK_ID ?? ""}` });
}

// ------------------------------------------------------------------------------------------- G-01
const profileSchema = z.object({
  name: z.string().trim().min(1, "Name is required").max(200),
  industry: z.string().trim().max(100).optional(),
  business_model: z.string().trim().max(100).optional(),
  customer_type: z.enum(["B2B", "B2C", "both"]).optional(),
  size_band: z.enum(["1-10", "11-50", "51-200", "201-1000", "1000+"]).optional(),
  currency: z.string().regex(/^[A-Z]{3}$/, "Use a 3-letter currency code").optional(),
  timezone: z.string().max(64).optional(),
  fiscal_year_start: z.string().regex(/^(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/, "Use MM-DD").optional(),
});

function blankToUndefined(form: FormData): Record<string, string | undefined> {
  const out: Record<string, string | undefined> = {};
  for (const [k, v] of form.entries()) out[k] = typeof v === "string" && v.trim() !== "" ? v : undefined;
  return out;
}

export async function updateOrgProfile(_: ActionState | null, form: FormData): Promise<ActionState> {
  const { membership } = await requireContext();
  const parsed = profileSchema.safeParse(blankToUndefined(form));
  if (!parsed.success) return { error: parsed.error.issues.map((i) => i.message).join("; ") };
  const { name, ...profile } = parsed.data;
  const result = await call(`/v1/orgs/${membership.org_id}/profile`, {
    method: "PATCH",
    org: membership.org_id,
    body: { name, business_profile: profile },
  });
  if (!result.ok) return { error: problemMessage(result.problem) };
  revalidatePath("/settings/org");
  return { ok: true, message: "Organisation profile saved." };
}

// ------------------------------------------------------------------------------------------- G-02
const inviteSchema = z.object({
  email: z.string().trim().toLowerCase().email("Enter a valid e-mail address"),
  role: z.enum(["owner", "admin", "data_manager", "analyst", "viewer", "billing"]),
});

export async function inviteMember(_: ActionState | null, form: FormData): Promise<ActionState> {
  const { membership } = await requireContext();
  const parsed = inviteSchema.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues.map((i) => i.message).join("; ") };
  const result = await call(`/v1/orgs/${membership.org_id}/invites`, { method: "POST", org: membership.org_id, body: parsed.data });
  if (!result.ok) return { error: problemMessage(result.problem) };
  revalidatePath("/settings/team");
  return { ok: true, message: `Invitation sent to ${parsed.data.email}.` };
}

export async function revokeInvite(form: FormData): Promise<void> {
  const { membership } = await requireContext();
  const id = z.string().uuid().parse(form.get("invite_id"));
  await call(`/v1/orgs/${membership.org_id}/invites/${id}`, { method: "DELETE", org: membership.org_id });
  revalidatePath("/settings/team");
}

export async function changeRole(_: ActionState | null, form: FormData): Promise<ActionState> {
  const { membership } = await requireContext();
  const id = z.string().uuid().safeParse(form.get("membership_id"));
  const role = inviteSchema.shape.role.safeParse(form.get("role"));
  if (!id.success || !role.success) return { error: "Invalid request." };
  const result = await call(`/v1/memberships/${id.data}`, { method: "PATCH", org: membership.org_id, body: { role: role.data } });
  if (!result.ok) return { error: problemMessage(result.problem) };
  revalidatePath("/settings/team");
  return { ok: true, message: "Role updated." };
}

export async function removeMember(form: FormData): Promise<void> {
  const { membership } = await requireContext();
  const id = z.string().uuid().parse(form.get("membership_id"));
  await call(`/v1/memberships/${id}`, { method: "DELETE", org: membership.org_id });
  revalidatePath("/settings/team");
}

// ------------------------------------------------------------------------------------- X-01 / G-06
export async function markNotificationRead(form: FormData): Promise<void> {
  const { membership } = await requireContext();
  const id = z.string().uuid().parse(form.get("notification_id"));
  await call(`/v1/notifications/${id}/read`, { method: "POST", org: membership.org_id });
  revalidatePath("/notifications");
  revalidatePath("/", "layout");
}

export async function markAllRead(): Promise<void> {
  const { membership } = await requireContext();
  await call("/v1/notifications/read-all", { method: "POST", org: membership.org_id });
  revalidatePath("/notifications");
  revalidatePath("/", "layout");
}

export async function savePreferences(_: ActionState | null, form: FormData): Promise<ActionState> {
  const { membership } = await requireContext();
  const types = form.getAll("event_type").map(String);
  const items = types.map((event_type) => ({
    event_type,
    email: form.get(`${event_type}:email`) === "on",
    in_app: form.get(`${event_type}:in_app`) === "on",
  }));
  const result = await call("/v1/notification-preferences", { method: "PUT", org: membership.org_id, body: { items } });
  if (!result.ok) return { error: problemMessage(result.problem) };
  revalidatePath("/settings/notifications");
  return { ok: true, message: "Preferences saved." };
}
