import type { Schemas } from "@dcs/api-client";
import Link from "next/link";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { Sidebar } from "@/components/shell/sidebar";
import { Topbar } from "@/components/shell/topbar";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { visibleNav } from "@/lib/nav";
import { outcomeOf } from "@/lib/problem";

export default async function AppLayout({ children }: { children: ReactNode }) {
  const { me, membership } = await requireContext();
  const org = membership.org_id;

  // Central gates: MFA step-up for owners/admins and maintenance mode (flags are evaluated per org).
  const flags = await call<Schemas["FlagsOut"]>("/v1/flags", { org });
  if (!flags.ok && outcomeOf(flags) === "mfa") redirect("/auth/mfa?returnTo=/");
  if (flags.ok && flags.data.flags["system.maintenance"] === true) redirect("/maintenance");

  const unread = await call<Schemas["Page_NotificationOut_"]>("/v1/notifications?unread_only=true&limit=100", { org });
  const unreadCount = unread.ok ? unread.data.items.length : 0;

  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 border-r border-border bg-sidebar md:block">
        <Link href="/" className="flex h-14 items-center gap-2 border-b border-border px-5 font-semibold">
          <svg viewBox="0 0 32 32" className="h-6 w-6" aria-hidden>
            <rect width="32" height="32" rx="7" fill="currentColor" className="text-primary" />
            <path d="M9 9h7a7 7 0 0 1 0 14H9z" fill="none" stroke="white" strokeWidth="3" />
          </svg>
          DCS-PIS
        </Link>
        <Sidebar items={visibleNav(membership.permissions)} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <Topbar me={me} membership={membership} unread={unreadCount} />
        <main className="mx-auto w-full max-w-6xl flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
