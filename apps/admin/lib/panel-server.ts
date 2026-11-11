import "server-only";

import type { ApiResult, Schemas } from "@dcs/api-client";

import { call } from "@/lib/api";

export type PanelLoad =
  | { ok: true; config: Schemas["ConfigOut"]; permissions: ReadonlySet<string> }
  | { ok: false; result: ApiResult<unknown> };

/** Control-panel settings plus the caller's staff permissions (to decide which editors are writable). */
export async function loadPanel(): Promise<PanelLoad> {
  const [config, me] = await Promise.all([
    call<Schemas["ConfigOut"]>("/v1/admin/config"),
    call<Schemas["StaffMeOut"]>("/v1/admin/me"),
  ]);
  if (!config.ok) return { ok: false, result: config };
  if (!me.ok) return { ok: false, result: me };
  return { ok: true, config: config.data, permissions: new Set(me.data.permissions) };
}
