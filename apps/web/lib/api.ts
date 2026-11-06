import "server-only";

import { redirect } from "next/navigation";

import { type ApiResult, toProblem } from "./problem";
import { getAccessToken, getSelectedOrgId } from "./session";

const CONTROL = process.env.CONTROL_API_URL ?? "http://localhost:8001";
const DATA = process.env.DATA_API_URL ?? "http://localhost:8002";

interface CallOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  body?: unknown;
  org?: string | false; // false = no org header; undefined = selected org
  idempotencyKey?: string;
  service?: "control" | "data";
  auth?: boolean;
}

/**
 * Server-side API call with the user's access token. Returns a typed result instead of throwing, so pages can
 * render the correct state. Missing/expired sessions redirect to sign-in.
 */
export async function call<T>(path: string, opts: CallOptions = {}): Promise<ApiResult<T>> {
  const headers: Record<string, string> = { accept: "application/json" };
  if (opts.auth !== false) {
    const session = await getAccessToken();
    if (!session) redirect("/session-expired");
    headers.authorization = `Bearer ${session.accessToken}`;
  }
  const org = opts.org === undefined ? await getSelectedOrgId() : opts.org;
  if (org) headers["x-dcs-org"] = org;
  if (opts.body !== undefined) headers["content-type"] = "application/json";
  if (opts.idempotencyKey) headers["idempotency-key"] = opts.idempotencyKey;
  const base = opts.service === "data" ? DATA : CONTROL;
  let resp: Response;
  try {
    resp = await fetch(`${base}${path}`, {
      method: opts.method ?? "GET",
      headers,
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
