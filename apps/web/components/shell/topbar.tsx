import type { Me, Membership } from "@dcs/api-client";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@dcs/ui";
import { CircleHelp, CircleUserRound, LogOut, Search, ShieldCheck } from "lucide-react";
import Link from "next/link";

import { signOutAction } from "@/app/actions";
import { t } from "@/lib/i18n";

import { NotificationBell } from "./live";
import { OrgSwitcher } from "./org-switcher";

export function Topbar({ me, membership, unread }: { me: Me; membership: Membership; unread: number }) {
  const accountUrl = `${process.env.AUTH_KEYCLOAK_ISSUER ?? ""}/account`;
  return (
    <header className="flex h-14 items-center gap-3 border-b border-border bg-background px-4">
      <OrgSwitcher memberships={me.memberships} activeOrgId={membership.org_id} />
      <div className="ml-2 hidden flex-1 md:block">
        <div className="flex max-w-md items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm text-muted-foreground">
          <Search className="h-4 w-4" aria-hidden />
          <span>{t("top.search")}</span>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-1">
        <NotificationBell orgId={membership.org_id} initialUnread={unread} realtimeUrl={process.env.NEXT_PUBLIC_REALTIME_URL} />
        <span className="rounded-md p-2 text-muted-foreground" title="Help & concierge arrive in a coming release">
          <CircleHelp className="h-4 w-4" aria-label={t("top.help")} />
        </span>
        <Menu>
          <MenuTrigger className="flex items-center gap-2 rounded-md p-1.5 hover:bg-muted" aria-label={t("top.profile")}>
            <CircleUserRound className="h-5 w-5" aria-hidden />
          </MenuTrigger>
          <MenuContent align="end">
            <MenuLabel>
              <span className="block font-medium text-foreground">{me.user.name ?? me.user.email}</span>
              <span className="block">{me.user.email}</span>
            </MenuLabel>
            <MenuSeparator />
            <MenuItem asChild>
              <a href={accountUrl} target="_blank" rel="noreferrer">
                <ShieldCheck className="h-4 w-4" aria-hidden /> {t("top.account")}
              </a>
            </MenuItem>
            <MenuItem asChild>
              <Link href="/settings/notifications">{t("nav.settings.notifications")}</Link>
            </MenuItem>
            <MenuSeparator />
            <form action={signOutAction}>
              <MenuItem asChild>
                <button type="submit" className="w-full">
                  <LogOut className="h-4 w-4" aria-hidden /> {t("top.signout")}
                </button>
              </MenuItem>
            </form>
          </MenuContent>
        </Menu>
      </div>
    </header>
  );
}
