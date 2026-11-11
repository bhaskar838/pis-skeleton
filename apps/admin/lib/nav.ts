/**
 * Admin console navigation, laid out like the car in SPEC §0 (ADR-0011): each group is a part of the car and
 * holds the controls for that part. Items that later phases fit are shown with the phase that brings them.
 */
export interface AdminNavItem {
  href: string;
  label: string;
  permission: string;
  /** Phase that builds this page; set while the page does not exist yet. */
  soon?: string;
}

export interface AdminNavGroup {
  part: string;
  hint: string;
  items: AdminNavItem[];
}

export const ADMIN_NAV_GROUPS: AdminNavGroup[] = [
  {
    part: "Dashboard",
    hint: "Gauges and warning lights",
    items: [{ href: "/", label: "Instrument cluster", permission: "platform:dashboard:read" }],
  },
  {
    part: "Cabin",
    hint: "The customers on board",
    items: [
      { href: "/tenants", label: "Tenants", permission: "platform:tenants:read" },
      { href: "/concierge", label: "Concierge queue", permission: "platform:tenants:read", soon: "P2" },
    ],
  },
  {
    part: "Chassis",
    hint: "Regions, launch countries, limits",
    items: [{ href: "/chassis", label: "Regions & limits", permission: "platform:config:read" }],
  },
  {
    part: "Body",
    hint: "What customers see",
    items: [{ href: "/body", label: "Brand & legal", permission: "platform:config:read" }],
  },
  {
    part: "Electricals",
    hint: "Integrations and API keys",
    items: [{ href: "/electricals", label: "Integrations & secrets", permission: "platform:config:read" }],
  },
  {
    part: "Trims & options",
    hint: "Plans, add-ons and prices",
    items: [
      { href: "/trims", label: "Service prices", permission: "platform:config:read" },
      { href: "/plans", label: "Plans & pricing", permission: "platform:config:read", soon: "P8" },
    ],
  },
  {
    part: "Wheels",
    hint: "Floor 1: data in",
    items: [
      { href: "/wheels", label: "Acquisition", permission: "platform:config:read" },
      { href: "/connectors", label: "Connectors", permission: "platform:tenants:read", soon: "P4" },
      { href: "/bridge", label: "Bridge agents", permission: "platform:tenants:read", soon: "P5" },
      { href: "/recipes", label: "Browser recipes", permission: "platform:tenants:read", soon: "P6" },
    ],
  },
  {
    part: "Fuel lines",
    hint: "Floor 2: shaping data",
    items: [
      { href: "/fuel-lines", label: "Shaping", permission: "platform:config:read" },
      { href: "/model", label: "CBM & templates", permission: "platform:tenants:read", soon: "P2" },
      { href: "/llm", label: "Model gateway", permission: "platform:dashboard:read", soon: "P2" },
    ],
  },
  {
    part: "Engine bay",
    hint: "Floor 3: tools",
    items: [
      { href: "/engine-bay", label: "Engine socket", permission: "platform:config:read" },
      { href: "/tools", label: "Tool registry", permission: "platform:tenants:read", soon: "P3" },
    ],
  },
  {
    part: "Switchgear",
    hint: "Flags and kill switches",
    items: [{ href: "/settings", label: "Feature flags", permission: "platform:flags:read" }],
  },
  {
    part: "Locks & keys",
    hint: "Audit and staff access",
    items: [{ href: "/security", label: "Audit & staff access", permission: "platform:audit:read" }],
  },
];

export const ADMIN_NAV: AdminNavItem[] = ADMIN_NAV_GROUPS.flatMap((g) => g.items);

export function visibleAdminNav(permissions: Iterable<string>): AdminNavGroup[] {
  const perms = new Set(permissions);
  return ADMIN_NAV_GROUPS.map((g) => ({ ...g, items: g.items.filter((i) => perms.has(i.permission)) })).filter(
    (g) => g.items.length > 0,
  );
}

export function isActive(href: string, pathname: string): boolean {
  return href === "/" ? pathname === "/" : pathname === href || pathname.startsWith(`${href}/`);
}
