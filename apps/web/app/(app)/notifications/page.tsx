import type { NotificationItem, Schemas } from "@dcs/api-client";
import { Badge, Button, Card, EmptyState, ForbiddenState, PageHeader, relativeTime } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { markAllRead, markNotificationRead } from "@/app/actions";
import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { can } from "@/lib/org";

export const metadata: Metadata = { title: "Notifications" };

// X-01: notification centre with deep links.
export default async function NotificationsPage({ searchParams }: { searchParams: Promise<{ cursor?: string }> }) {
  const { membership } = await requireContext();
  if (!can(membership, "notifications:read")) return <ForbiddenState />;
  const { cursor } = await searchParams;
  const qs = new URLSearchParams({ limit: "30" });
  if (cursor) qs.set("cursor", cursor);
  const page = await call<Schemas["Page_NotificationOut_"]>(`/v1/notifications?${qs}`, { org: membership.org_id });
  if (!page.ok) return <ApiState result={page} returnTo="/notifications" />;
  const items = page.data.items;
  const unread = items.some((n) => !n.read_at);
  return (
    <>
      <PageHeader
        title="Notifications"
        description={membership.org_name}
        actions={
          unread ? (
            <form action={markAllRead}>
              <Button type="submit" variant="outline" size="sm">
                Mark all as read
              </Button>
            </form>
          ) : null
        }
      />
      {items.length === 0 ? (
        <EmptyState title="You're all caught up" description="Notifications about your workspace and team appear here." />
      ) : (
        <Card className="divide-y divide-border">
          {items.map((n: NotificationItem) => (
            <div key={n.id} className="flex items-start justify-between gap-4 p-4">
              <div>
                <div className="flex items-center gap-2">
                  <span className="font-medium">{TITLES[n.type] ?? n.type}</span>
                  {!n.read_at ? <Badge tone="primary">New</Badge> : null}
                </div>
                {typeof n.payload.message === "string" ? <p className="mt-1 text-sm text-muted-foreground">{n.payload.message}</p> : null}
                <p className="mt-1 text-xs text-muted-foreground">{relativeTime(n.created_at)}</p>
              </div>
              {!n.read_at ? (
                <form action={markNotificationRead}>
                  <input type="hidden" name="notification_id" value={n.id} />
                  <Button type="submit" variant="ghost" size="sm">
                    Mark read
                  </Button>
                </form>
              ) : null}
            </div>
          ))}
        </Card>
      )}
      {page.data.next_cursor ? (
        <div className="mt-4 flex justify-end">
          <Button asChild variant="outline" size="sm">
            <Link href={`/notifications?cursor=${page.data.next_cursor}`}>Older</Link>
          </Button>
        </div>
      ) : null}
    </>
  );
}

const TITLES: Record<string, string> = {
  "tenant.provisioned": "Your workspace is ready",
  "member.joined": "A new member joined",
  "member.role_changed": "Your role changed",
  "member.removed": "You were removed from an organisation",
};
