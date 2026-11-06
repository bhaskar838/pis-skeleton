/** Admin console navigation (SPEC §9.3). Phase 0 builds M-01, M-02, M-03, M-12, M-13; others are shown as "soon". */
export interface AdminNavItem {
  href: string;
  label: string;
  permission: string;
  soon?: boolean;
}

export const ADMIN_NAV: AdminNavItem[] = [
  { href: "/", label: "Dashboard", permission: "platform:dashboard:read" },
  { href: "/tenants", label: "Tenants", permission: "platform:tenants:read" },
  { href: "/connectors", label: "Connectors", permission: "platform:tenants:read", soon: true },
  { href: "/recipes", label: "Browser recipes", permission: "platform:tenants:read", soon: true },
  { href: "/bridge", label: "Bridge agents", permission: "platform:tenants:read", soon: true },
  { href: "/model", label: "CBM & templates", permission: "platform:tenants:read", soon: true },
  { href: "/concierge", label: "Concierge", permission: "platform:tenants:read", soon: true },
  { href: "/tools", label: "Tool registry", permission: "platform:tenants:read", soon: true },
  { href: "/plans", label: "Plans & pricing", permission: "platform:flags:read", soon: true },
  { href: "/llm", label: "LLM usage", permission: "platform:dashboard:read", soon: true },
  { href: "/security", label: "Audit & staff access", permission: "platform:audit:read" },
  { href: "/settings", label: "Settings & flags", permission: "platform:flags:read" },
];

export function visibleAdminNav(permissions: Iterable<string>): AdminNavItem[] {
  const perms = new Set(permissions);
  return ADMIN_NAV.filter((i) => perms.has(i.permission));
}

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
