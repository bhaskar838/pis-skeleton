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

export const COUNTRIES: { code: string; name: string }[] = [
  { code: "IN", name: "India" },
  { code: "GB", name: "United Kingdom" },
  { code: "IE", name: "Ireland" },
  { code: "DE", name: "Germany" },
  { code: "FR", name: "France" },
  { code: "NL", name: "Netherlands" },
  { code: "ES", name: "Spain" },
  { code: "IT", name: "Italy" },
  { code: "AE", name: "United Arab Emirates" },
  { code: "SG", name: "Singapore" },
  { code: "US", name: "United States" },
  { code: "AU", name: "Australia" },
];

export function regionLabel(region: string): string {
  return region === "eu-west-2" ? "UK / EU (London)" : region === "ap-south-1" ? "India (Mumbai)" : region;
}
