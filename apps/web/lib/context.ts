import "server-only";

import type { Me, Membership } from "@dcs/api-client";
import { redirect } from "next/navigation";
import { cache } from "react";

import { call } from "./api";
import { pickMembership } from "./org";
import { outcomeOf } from "./problem";
import { getSelectedOrgId } from "./session";

export interface AppContext {
  me: Me;
  membership: Membership;
}

/** Current user + active membership, fetched once per request. Redirects when there is no usable session/org. */
export const requireContext = cache(async (): Promise<AppContext> => {
  const me = await call<Me>("/v1/me", { org: false });
  if (!me.ok) {
    const outcome = outcomeOf(me);
    if (outcome === "unauthenticated") redirect("/session-expired");
    throw new Error(`could not load session (${me.status})`);
  }
  const membership = pickMembership(me.data, await getSelectedOrgId());
  if (!membership) redirect("/auth/sign-up");
  return { me: me.data, membership };
});
