import type { AuditEvent, Schemas } from "@dcs/api-client";
import { Badge, Button, EmptyState, PageHeader, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";

import { runVerification } from "@/app/actions";
import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";

export const metadata: Metadata = { title: "Audit & staff access" };

// M-12: hash-chain verification status, staff actions. Break-glass approvals arrive with the break-glass flow.
export default async function SecurityPage() {
  const [verification, staff] = await Promise.all([
    call<Schemas["VerificationRunOut"][]>("/v1/admin/audit/verification"),
    call<Schemas["Page_AuditEventOut_"]>("/v1/admin/audit?actor_type=staff&limit=50"),
  ]);
  return (
    <>
      <PageHeader
        title="Audit & staff access"
        description="Audit-log integrity and every action taken by DCS staff."
        actions={
          <form action={runVerification}>
            <Button type="submit" variant="outline" size="sm">
              Verify chains now
            </Button>
          </form>
        }
      />
      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Hash-chain verification</h2>
      {!verification.ok ? (
        <ApiState result={verification} />
      ) : verification.data.length === 0 ? (
        <EmptyState title="Not verified yet" description="The nightly job runs at 02:00 UTC, or verify now." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Chain</TH>
              <TH>Result</TH>
              <TH>Events</TH>
              <TH>Checked at</TH>
              <TH>Problem</TH>
            </TR>
          </THead>
          <TBody>
            {verification.data.map((r) => (
              <TR key={r.chain}>
                <TD className="font-mono text-xs">{r.chain === "00000000-0000-0000-0000-000000000000" ? "platform" : r.chain}</TD>
                <TD>
                  <Badge tone={r.ok ? "success" : "danger"}>{r.ok ? "intact" : "TAMPERED"}</Badge>
                </TD>
                <TD>{r.checked}</TD>
                <TD className="text-xs">{r.ran_at.replace("T", " ").slice(0, 19)}</TD>
                <TD className="text-xs text-destructive">{r.ok ? "" : `${r.reason} (event ${r.first_bad_id})`}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}

      <h2 className="mb-2 mt-8 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Staff actions</h2>
      {!staff.ok ? (
        <ApiState result={staff} />
      ) : staff.data.items.length === 0 ? (
        <EmptyState title="No staff actions recorded" />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>When (UTC)</TH>
              <TH>Staff</TH>
              <TH>Action</TH>
              <TH>Tenant</TH>
            </TR>
          </THead>
          <TBody>
            {staff.data.items.map((e: AuditEvent) => (
              <TR key={e.id}>
                <TD className="font-mono text-xs">{e.ts.replace("T", " ").slice(0, 19)}</TD>
                <TD className="text-xs">{e.actor_id}</TD>
                <TD className="font-mono text-xs">{e.action}</TD>
                <TD className="font-mono text-xs">{e.org_id ?? "platform"}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
      <h2 className="mb-2 mt-8 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Break-glass approvals</h2>
      <EmptyState title="No break-glass requests" description="Time-boxed, owner-approved access to tenant data arrives in a later phase." />
    </>
  );
}
