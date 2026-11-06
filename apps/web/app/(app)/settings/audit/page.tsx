import type { AuditEvent, Schemas } from "@dcs/api-client";
import { Badge, Button, EmptyState, ForbiddenState, Input, PageHeader, Select, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { can } from "@/lib/org";

export const metadata: Metadata = { title: "Audit log" };

const ACTOR_TONES: Record<string, "primary" | "warning" | "neutral"> = { user: "primary", staff: "warning", system: "neutral" };

// G-04: append-only, hash-chained audit trail — including any DCS staff access to this organisation.
export default async function AuditPage({
  searchParams,
}: {
  searchParams: Promise<{ action?: string; actor_type?: string; cursor?: string }>;
}) {
  const { membership } = await requireContext();
  if (!can(membership, "audit:read")) return <ForbiddenState />;
  const sp = await searchParams;
  const qs = new URLSearchParams({ limit: "50" });
  if (sp.action) qs.set("action", sp.action);
  if (sp.actor_type) qs.set("actor_type", sp.actor_type);
  if (sp.cursor) qs.set("cursor", sp.cursor);
  const page = await call<Schemas["Page_AuditEventOut_"]>(`/v1/audit?${qs}`, { org: membership.org_id });
  if (!page.ok) return <ApiState result={page} returnTo="/settings/audit" />;
  const next = new URLSearchParams(qs);
  next.delete("limit");
  if (page.data.next_cursor) next.set("cursor", page.data.next_cursor);

  return (
    <>
      <PageHeader title="Audit log" description="Every change, sign-in-relevant action and staff access, in order." />
      <form className="mb-4 flex flex-wrap items-end gap-2" method="get">
        <Input name="action" placeholder="Action starts with… e.g. member." defaultValue={sp.action ?? ""} className="w-64" aria-label="Action filter" />
        <Select name="actor_type" defaultValue={sp.actor_type ?? ""} className="w-40" aria-label="Actor filter">
          <option value="">All actors</option>
          <option value="user">People</option>
          <option value="staff">DCS staff</option>
          <option value="system">System</option>
        </Select>
        <Button type="submit" variant="outline">
          Filter
        </Button>
      </form>
      {page.data.items.length === 0 ? (
        <EmptyState title="No events match" description="Try removing a filter." />
      ) : (
        <>
          <Table>
            <THead>
              <TR>
                <TH>When (UTC)</TH>
                <TH>Actor</TH>
                <TH>Action</TH>
                <TH>Target</TH>
                <TH>Details</TH>
              </TR>
            </THead>
            <TBody>
              {page.data.items.map((e: AuditEvent) => (
                <TR key={e.id}>
                  <TD className="whitespace-nowrap font-mono text-xs">{e.ts.replace("T", " ").slice(0, 19)}</TD>
                  <TD>
                    <Badge tone={ACTOR_TONES[e.actor_type] ?? "neutral"}>{e.actor_type}</Badge>
                  </TD>
                  <TD className="font-mono text-xs">{e.action}</TD>
                  <TD className="text-xs text-muted-foreground">{e.target_type ?? "—"}</TD>
                  <TD className="max-w-sm truncate font-mono text-xs text-muted-foreground" title={JSON.stringify(e.details)}>
                    {Object.keys(e.details).length ? JSON.stringify(e.details) : "—"}
                  </TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {page.data.next_cursor ? (
            <div className="mt-4 flex justify-end">
              <Button asChild variant="outline" size="sm">
                <Link href={`/settings/audit?${next}`}>Older events</Link>
              </Button>
            </div>
          ) : null}
        </>
      )}
    </>
  );
}
