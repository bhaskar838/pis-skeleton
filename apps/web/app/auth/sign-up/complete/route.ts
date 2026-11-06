// A-02 completion: after Keycloak registration, create the organisation remembered in the pending cookie.
import { cookies } from "next/headers";
import { NextResponse } from "next/server";

import { call } from "@/lib/api";
import { problemMessage } from "@/lib/problem";
import { ORG_COOKIE, PENDING_ORG_COOKIE } from "@/lib/session";

export async function GET(request: Request) {
  const jar = await cookies();
  const raw = jar.get(PENDING_ORG_COOKIE)?.value;
  const base = new URL(request.url);
  const origin = process.env.AUTH_URL ?? base.origin;
  if (!raw) return NextResponse.redirect(new URL("/auth/sign-up", origin));
  let pending: { name: string; country: string; key: string };
  try {
    pending = JSON.parse(raw) as typeof pending;
  } catch {
    jar.delete(PENDING_ORG_COOKIE);
    return NextResponse.redirect(new URL("/auth/sign-up", origin));
  }
  const result = await call<{ id: string }>("/v1/orgs", {
    method: "POST",
    org: false,
    body: { name: pending.name, country: pending.country },
    idempotencyKey: pending.key,
  });
  if (!result.ok) {
    const url = new URL("/auth/sign-up", origin);
    url.searchParams.set("error", problemMessage(result.problem));
    return NextResponse.redirect(url);
  }
  const response = NextResponse.redirect(new URL("/", origin));
  response.cookies.delete(PENDING_ORG_COOKIE);
  response.cookies.set(ORG_COOKIE, result.data.id, { httpOnly: true, sameSite: "lax", path: "/", maxAge: 31536000 });
  return response;
}
