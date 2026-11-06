/**
 * Typed clients for control-api and data-api, generated from their OpenAPI specs (`make codegen`).
 * Server-side only in the apps: access tokens never reach browser JavaScript (see apps/web/lib/api.ts).
 */
import createClient, { type Middleware } from "openapi-fetch";

import type { components as ControlComponents, paths as ControlPaths } from "./generated/control";
import type { paths as DataPaths } from "./generated/data";

export type { ControlPaths, DataPaths };
export type Schemas = ControlComponents["schemas"];
export type Me = Schemas["MeOut"];
export type Membership = Schemas["MembershipSummary"];
export type Org = Schemas["OrgOut"];
export type Team = Schemas["TeamOut"];
export type Member = Schemas["MemberOut"];
export type Invite = Schemas["InviteOut"];
export type AuditEvent = Schemas["AuditEventOut"];
export type NotificationItem = Schemas["NotificationOut"];
export type TenantRow = Schemas["TenantRow"];
export type TenantDetail = Schemas["TenantDetail"];
export type CustomerRole = Membership["role"];

/** RFC 9457 problem details as returned by every DCS API. */
export interface Problem {
  type: string;
  title: string;
  status: number;
  detail?: string;
  instance?: string;
  permission?: string;
  step_up_acr?: string;
  errors?: { loc: (string | number)[]; msg: string; type: string }[];
}

export interface ClientOptions {
  baseUrl: string;
  accessToken?: string;
  orgId?: string;
  fetch?: typeof fetch;
}

function authMiddleware(opts: ClientOptions): Middleware {
  return {
    onRequest({ request }) {
      if (opts.accessToken) request.headers.set("Authorization", `Bearer ${opts.accessToken}`);
      if (opts.orgId) request.headers.set("X-DCS-Org", opts.orgId);
      return request;
    },
  };
}

export function createControlClient(opts: ClientOptions) {
  const client = createClient<ControlPaths>({ baseUrl: opts.baseUrl, fetch: opts.fetch });
  client.use(authMiddleware(opts));
  return client;
}

export function createDataClient(opts: ClientOptions) {
  const client = createClient<DataPaths>({ baseUrl: opts.baseUrl, fetch: opts.fetch });
  client.use(authMiddleware(opts));
  return client;
}

/** Slug of a problem type, e.g. "mfa-required" from "https://errors.dcs-pis.app/mfa-required". */
export function problemSlug(problem: Pick<Problem, "type"> | undefined | null): string | undefined {
  if (!problem?.type) return undefined;
  const parts = problem.type.split("/");
  return parts[parts.length - 1] || undefined;
}

export function isProblem(value: unknown): value is Problem {
  return (
    typeof value === "object" &&
    value !== null &&
    typeof (value as Problem).type === "string" &&
    typeof (value as Problem).status === "number"
  );
}

export { type ApiResult, outcomeOf, type PageOutcome, problemMessage, toProblem } from "./result";
