"use server";

import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { z } from "zod";

import { signIn } from "@/auth";
import { call } from "@/lib/api";
import { problemMessage } from "@/lib/problem";
import { ORG_COOKIE, PENDING_ORG_COOKIE } from "@/lib/session";

import type { ActionState } from "../actions";

const orgSchema = z.object({
  name: z.string().trim().min(1, "Company name is required").max(200),
  country: z.string().regex(/^[A-Z]{2}$/, "Choose a country"),
});

function safeReturnTo(value: FormDataEntryValue | null): string {
  const s = typeof value === "string" ? value : "/";
  return s.startsWith("/") && !s.startsWith("//") ? s : "/";
}

/** A-01: start Keycloak sign-in (optionally stepping up to MFA). */
export async function startSignIn(form: FormData): Promise<void> {
  const returnTo = safeReturnTo(form.get("returnTo"));
  const params: Record<string, string> = form.get("stepUp") === "1" ? { acr_values: "mfa" } : {};
  await signIn("keycloak", { redirectTo: returnTo }, params);
}

/** A-04: force a second factor (Keycloak shows OTP/WebAuthn enrolment if none is configured). */
export async function startStepUp(form: FormData): Promise<void> {
  // prompt=login re-confirms the password before a second factor is added or used (then TOTP, enrolled on first use).
  await signIn("keycloak", { redirectTo: safeReturnTo(form.get("returnTo")) }, { acr_values: "mfa", prompt: "login" });
}

/** A-02 (new visitor): remember company + country, then open Keycloak registration. */
export async function startSignUp(_: ActionState | null, form: FormData): Promise<ActionState> {
  const parsed = orgSchema.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues.map((i) => i.message).join("; ") };
  const pending = { ...parsed.data, key: crypto.randomUUID() };
  (await cookies()).set(PENDING_ORG_COOKIE, JSON.stringify(pending), {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.AUTH_URL?.startsWith("https"),
    path: "/",
    maxAge: 60 * 60,
  });
  await signIn("keycloak", { redirectTo: "/auth/sign-up/complete" }, { prompt: "create" });
  return { ok: true };
}

/** A-02 (signed-in user without an org, or "New organisation"): create the org directly. */
export async function createOrganisation(_: ActionState | null, form: FormData): Promise<ActionState> {
  const parsed = orgSchema.safeParse(Object.fromEntries(form));
  if (!parsed.success) return { error: parsed.error.issues.map((i) => i.message).join("; ") };
  const result = await call<{ id: string }>("/v1/orgs", {
    method: "POST",
    org: false,
    body: parsed.data,
    idempotencyKey: String(form.get("idempotency_key") ?? crypto.randomUUID()),
  });
  if (!result.ok) return { error: problemMessage(result.problem) };
  (await cookies()).set(ORG_COOKIE, result.data.id, { httpOnly: true, sameSite: "lax", path: "/", maxAge: 31536000 });
  redirect("/");
}

/** A-05: accept an invitation as the signed-in user. */
export async function acceptInvite(_: ActionState | null, form: FormData): Promise<ActionState> {
  const token = z.string().min(20).max(100).safeParse(form.get("token"));
  if (!token.success) return { error: "Invalid invitation link." };
  const result = await call<{ org_id: string }>(`/v1/invites/${token.data}/accept`, { method: "POST", org: false });
  if (!result.ok) return { error: problemMessage(result.problem) };
  (await cookies()).set(ORG_COOKIE, result.data.org_id, { httpOnly: true, sameSite: "lax", path: "/", maxAge: 31536000 });
  redirect("/");
}
