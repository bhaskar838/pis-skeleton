import type { Schemas, TenantDetail } from "@dcs/api-client";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, Notice, PageHeader, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";

import { retryProvisioning } from "@/app/actions";
import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";

import { DeprovisionForm } from "./deprovision-form";

export const metadata: Metadata = { title: "Tenant" };

// M-03 (basic): profile, provisioning state, key status (never key material), recent audit, deprovision.
// Viewing this page is itself audited into the tenant's chain (visible to the customer in G-04).
export default async function TenantPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const [detail, me] = await Promise.all([
    call<TenantDetail>(`/v1/admin/tenants/${id}`),
    call<Schemas["StaffMeOut"]>("/v1/admin/me"),
  ]);
  if (!detail.ok) return <ApiState result={detail} />;
  const t = detail.data;
  const perms = me.ok ? me.data.permissions : [];
  const canDeprovision = perms.includes("platform:tenants:deprovision") && !["deleted", "deprovisioning"].includes(t.org.status);
  const canRetry = perms.includes("platform:tenants:write") && ["failed", "provisioning"].includes(t.org.status);

  return (
    <>
      <PageHeader
        title={t.org.name}
        description={`${t.org.slug} · ${t.org.tenant_id} · ${t.org.region}`}
        actions={<Badge tone={t.org.status === "active" ? "success" : "warning"}>{t.org.status}</Badge>}
      />
      <Notice>Staff see metadata only. Access to tenant data requires an approved break-glass ticket (coming in a later phase).</Notice>
      <div className="mt-4 grid gap-4 md:grid-cols-3">
        <Card>
          <CardHeader>
            <CardTitle>Database</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {t.db ? (
              <dl className="grid grid-cols-2 gap-1">
                <dt className="text-muted-foreground">Name</dt>
                <dd className="font-mono">{String(t.db.db_name)}</dd>
                <dt className="text-muted-foreground">Status</dt>
                <dd>{String(t.db.status)}</dd>
                <dt className="text-muted-foreground">CBM</dt>
                <dd>{String(t.db.cbm_version ?? "—")}</dd>
              </dl>
            ) : (
              "Not created"
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Encryption key</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {t.key ? (
              <dl className="grid grid-cols-2 gap-1">
                <dt className="text-muted-foreground">Provider</dt>
                <dd>{String(t.key.provider)}</dd>
                <dt className="text-muted-foreground">Status</dt>
                <dd>{String(t.key.status)}</dd>
                <dt className="text-muted-foreground">Deletion</dt>
                <dd>{t.key.deletion_scheduled_at ? String(t.key.deletion_scheduled_at).slice(0, 10) : "—"}</dd>
              </dl>
            ) : (
              "Not created"
            )}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>People</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <p>{t.member_count} active member(s)</p>
            <p className="mt-1 text-muted-foreground">Owner(s): {t.owners.join(", ") || "—"}</p>
          </CardContent>
        </Card>
      </div>

      {canRetry ? (
        <form action={retryProvisioning} className="mt-4">
          <input type="hidden" name="org_id" value={t.org.id} />
          <Button type="submit" variant="outline">
            Retry provisioning
          </Button>
        </form>
      ) : null}

      <h2 className="mb-2 mt-8 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Recent audit events</h2>
      {t.recent_audit.length === 0 ? (
        <EmptyState title="No events" />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>When (UTC)</TH>
              <TH>Actor</TH>
              <TH>Action</TH>
            </TR>
          </THead>
          <TBody>
            {t.recent_audit.map((e) => (
              <TR key={e.id}>
                <TD className="font-mono text-xs">{e.ts.replace("T", " ").slice(0, 19)}</TD>
                <TD>{e.actor_type}</TD>
                <TD className="font-mono text-xs">{e.action}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      {canDeprovision ? (
        <Card className="mt-8 border-destructive/40">
          <CardHeader>
            <CardTitle className="text-destructive">Deprovision tenant</CardTitle>
          </CardHeader>
          <CardContent>
            <DeprovisionForm orgId={t.org.id} slug={t.org.slug} />
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
