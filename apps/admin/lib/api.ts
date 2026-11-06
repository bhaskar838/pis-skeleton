import "server-only";

import { type ApiResult, toProblem } from "@dcs/api-client";
import { getToken } from "next-auth/jwt";
import { headers } from "next/headers";
import { redirect } from "next/navigation";

const CONTROL = process.env.CONTROL_API_URL ?? "http://localhost:8001";

export async function getAccessToken(): Promise<{ accessToken: string; idToken?: string } | null> {
  const secure = (process.env.AUTH_URL ?? "").startsWith("https://");
  const token = await getToken({
    req: { headers: await headers() },
    secret: process.env.AUTH_SECRET ?? "",
    secureCookie: secure,
    salt: secure ? "__Secure-authjs.session-token" : "authjs.session-token",
  });
  if (!token?.access_token || token.error) return null;
  return { accessToken: token.access_token, idToken: token.id_token };
}

/** Staff API call (`/v1/admin/*`). Staff tokens never carry an org header: staff see tenant metadata only. */
export async function call<T>(path: string, opts: { method?: string; body?: unknown } = {}): Promise<ApiResult<T>> {
  const session = await getAccessToken();
  if (!session) redirect("/auth/sign-in");
  const h: Record<string, string> = { accept: "application/json", authorization: `Bearer ${session.accessToken}` };
  if (opts.body !== undefined) h["content-type"] = "application/json";
  let resp: Response;
  try {
    resp = await fetch(`${CONTROL}${path}`, {
      method: opts.method ?? "GET",
      headers: h,
      body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
      cache: "no-store",
    });
  } catch {
    return { ok: false, status: 503, problem: { type: "about:blank", title: "Service unavailable", status: 503 } };
  }
  const text = await resp.text();
  const body: unknown = text ? JSON.parse(text) : null;
  if (!resp.ok) return { ok: false, status: resp.status, problem: toProblem(resp.status, body) };
  return { ok: true, status: resp.status, data: body as T };
}
