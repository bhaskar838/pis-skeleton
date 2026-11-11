import type { Me, Membership } from "@dcs/api-client";

/** Pick the active membership: the cookie's org if the user still belongs to it, else the first one. */
export function pickMembership(me: Me, selectedOrgId: string | undefined): Membership | undefined {
  return me.memberships.find((m) => m.org_id === selectedOrgId) ?? me.memberships[0];
}

export function can(membership: Membership | undefined, permission: string): boolean {
  return Boolean(membership?.permissions.includes(permission));
}

/** Roles the actor may grant (mirrors policies.yaml `can_assign`; the API re-checks). */
export function assignableRoles(role: Membership["role"] | undefined): Membership["role"][] {
  if (role === "owner") return ["owner", "admin", "data_manager", "analyst", "viewer", "billing"];
  if (role === "admin") return ["admin", "data_manager", "analyst", "viewer", "billing"];
  return [];
}

export const ROLE_LABELS: Record<Membership["role"], string> = {
  owner: "Owner",
  admin: "Admin",
  data_manager: "Data Manager",
  analyst: "Analyst",
  viewer: "Viewer",
  billing: "Billing",
};

// AWS region display names. Which regions exist and which countries map to them is set in the control panel.
const REGION_NAMES: Record<string, string> = {
  "ap-south-1": "India (Mumbai)",
  "eu-west-2": "UK / Europe (London)",
  "us-east-1": "Americas (N. Virginia)",
  "ap-southeast-1": "Asia-Pacific (Singapore)",
  "sa-east-1": "South America (São Paulo)",
  "ap-southeast-2": "Australia (Sydney)",
};

export function regionLabel(region: string): string {
  return REGION_NAMES[region] ?? region;
}
