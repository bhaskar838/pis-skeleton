import type { Schemas, TenantRow } from "@dcs/api-client";
import { Badge, Button, EmptyState, Input, PageHeader, Select, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";

export const metadata: Metadata = { title: "Tenants" };

const TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  active: "success",
  provisioning: "warning",
  deprovisioning: "warning",
  failed: "danger",
  deleted: "neutral",
};

// M-02: search, status, region, health (filters synced to the URL; server-side pagination).
export default async function TenantsPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string; status?: string; region?: string; cursor?: string }>;
}) {
  const sp = await searchParams;
  const qs = new URLSearchParams({ limit: "50" });
  for (const k of ["q", "status", "region", "cursor"] as const) if (sp[k]) qs.set(k, sp[k] as string);
  const page = await call<Schemas["Page_TenantRow_"]>(`/v1/admin/tenants?${qs}`);
  if (!page.ok) return <ApiState result={page} />;
  const next = new URLSearchParams(qs);
  next.delete("limit");
  if (page.data.next_cursor) next.set("cursor", page.data.next_cursor);

  return (
    <>
      <PageHeader title="Tenants" description="Every customer organisation and its provisioning state." />
      <form method="get" className="mb-4 flex flex-wrap gap-2">
        <Input name="q" placeholder="Name, slug or tenant id" defaultValue={sp.q ?? ""} className="w-64" aria-label="Search" />
        <Select name="status" defaultValue={sp.status ?? ""} className="w-44" aria-label="Status">
          <option value="">Any status</option>
          {Object.keys(TONE).map((s) => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </Select>
        <Select name="region" defaultValue={sp.region ?? ""} className="w-44" aria-label="Region">
          <option value="">Any region</option>
          <option value="ap-south-1">ap-south-1</option>
          <option value="eu-west-2">eu-west-2</option>
        </Select>
        <Button type="submit" variant="outline">
          Filter
        </Button>
      </form>
      {page.data.items.length === 0 ? (
        <EmptyState title="No tenants match" description="Tenants appear here as soon as someone signs up." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>Tenant</TH>
              <TH>Region</TH>
              <TH>Status</TH>
              <TH>Database</TH>
              <TH>Created</TH>
            </TR>
          </THead>
          <TBody>
            {page.data.items.map((t: TenantRow) => (
              <TR key={t.org_id}>
                <TD>
                  <Link href={`/tenants/${t.org_id}`} className="font-medium text-primary hover:underline">
                    {t.name}
                  </Link>
                  <div className="text-xs text-muted-foreground">{t.slug}</div>
                </TD>
                <TD className="font-mono text-xs">{t.tenant_id}</TD>
                <TD>{t.region}</TD>
                <TD>
                  <Badge tone={TONE[t.status] ?? "neutral"}>{t.status}</Badge>
                </TD>
                <TD>{t.db_status ?? "—"}</TD>
                <TD className="text-xs">{t.created_at.slice(0, 10)}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      {page.data.next_cursor ? (
        <div className="mt-4 flex justify-end">
          <Button asChild variant="outline" size="sm">
            <Link href={`/tenants?${next}`}>Next page</Link>
          </Button>
        </div>
      ) : null}
    </>
  );
}
