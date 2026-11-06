import type { Schemas } from "@dcs/api-client";
import { Badge, Button, ErrorState } from "@dcs/ui";
import { redirect } from "next/navigation";
import type { ReactNode } from "react";

import { staffSignOut } from "@/app/actions";
import { AdminSidebar } from "@/components/admin-sidebar";
import { call } from "@/lib/api";
import { visibleAdminNav } from "@/lib/nav";

export default async function ConsoleLayout({ children }: { children: ReactNode }) {
  const me = await call<Schemas["StaffMeOut"]>("/v1/admin/me");
  if (!me.ok) {
    if (me.status === 401 || me.status === 403) redirect("/auth/sign-in");
    return <ErrorState description="The control API is unavailable." />;
  }
  return (
    <div className="flex min-h-screen">
      <aside className="hidden w-60 shrink-0 border-r border-border bg-sidebar md:block">
        <div className="flex h-14 items-center gap-2 border-b border-border px-5 font-semibold">
          DCS-PIS <Badge tone="warning">Staff</Badge>
        </div>
        <AdminSidebar items={visibleAdminNav(me.data.permissions)} />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 items-center justify-end gap-3 border-b border-border px-4 text-sm">
          <span className="text-muted-foreground">{me.data.email ?? me.data.subject}</span>
          {me.data.roles.map((r) => (
            <Badge key={r} tone="primary">
              {r}
            </Badge>
          ))}
          <form action={staffSignOut}>
            <Button type="submit" variant="ghost" size="sm">
              Sign out
            </Button>
          </form>
        </header>
        <main className="mx-auto w-full max-w-6xl flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
