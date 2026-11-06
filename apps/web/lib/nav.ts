/**
 * Customer app navigation (SPEC §9.1). The UI hides what a role cannot do; the API enforces it (SPEC §8.3).
 * Sections whose pages arrive in later phases are shown (for roles that may use them) but disabled.
 */
import type { MessageKey } from "./i18n";

export type IconName = "home" | "sources" | "studio" | "toolkit" | "insights" | "billing" | "settings";

export interface NavItem {
  id: string;
  href: string;
  label: MessageKey;
  permission: string;
  icon?: IconName;
  soon?: boolean;
  children?: NavItem[];
}

export const NAV: NavItem[] = [
  { id: "home", href: "/", label: "nav.home", icon: "home", permission: "org:read" },
  { id: "sources", href: "/sources", label: "nav.sources", icon: "sources", permission: "sources:read", soon: true },
  { id: "studio", href: "/studio/datasets", label: "nav.studio", icon: "studio", permission: "studio:read", soon: true },
  { id: "toolkit", href: "/toolkit/recommendation", label: "nav.toolkit", icon: "toolkit", permission: "tools:read", soon: true },
  { id: "insights", href: "/insights", label: "nav.insights", icon: "insights", permission: "insights:read", soon: true },
  { id: "billing", href: "/billing", label: "nav.billing", icon: "billing", permission: "billing:read", soon: true },
  {
    id: "settings",
    href: "/settings/org",
    label: "nav.settings",
    icon: "settings",
    permission: "org:read",
    children: [
      { id: "settings-org", href: "/settings/org", label: "nav.settings.org", permission: "org:read" },
      { id: "settings-team", href: "/settings/team", label: "nav.settings.team", permission: "members:read" },
      { id: "settings-security", href: "/settings/security", label: "nav.settings.security", permission: "security:read" },
      { id: "settings-audit", href: "/settings/audit", label: "nav.settings.audit", permission: "audit:read" },
      {
        id: "settings-notifications",
        href: "/settings/notifications",
        label: "nav.settings.notifications",
        permission: "notifications:read",
      },
    ],
  },
];

/** Items (and children) the role's permission set allows. Parents with no visible children are dropped. */
export function visibleNav(permissions: Iterable<string>, items: NavItem[] = NAV): NavItem[] {
  const perms = new Set(permissions);
  const out: NavItem[] = [];
  for (const item of items) {
    if (!perms.has(item.permission)) continue;
    if (item.children) {
      const children = visibleNav(perms, item.children);
      if (children.length === 0) continue;
      out.push({ ...item, href: children[0]?.href ?? item.href, children });
    } else {
      out.push(item);
    }
  }
  return out;
}

export function isActive(href: string, pathname: string): boolean {
  if (href === "/") return pathname === "/";
  return pathname === href || pathname.startsWith(`${href}/`);
}

/** Permission required by each built page; used by pages and by tests that keep nav and pages consistent. */
export const PAGE_PERMISSIONS: Record<string, string> = {
  "/": "org:read",
  "/settings/org": "org:read",
  "/settings/team": "members:read",
  "/settings/security": "security:read",
  "/settings/audit": "audit:read",
  "/settings/notifications": "notifications:read",
  "/notifications": "notifications:read",
};
