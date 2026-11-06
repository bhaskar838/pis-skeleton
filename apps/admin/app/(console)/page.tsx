import type { Schemas } from "@dcs/api-client";
import { Card, CardContent, CardHeader, CardTitle, EmptyState, PageHeader } from "@dcs/ui";
import type { Metadata } from "next";

import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";

export const metadata: Metadata = { title: "Dashboard" };

// M-01 (Phase 0 shell): tenants, users, audit-chain health. Queue depth, LLM spend and sandbox use arrive later.
export default async function Dashboard() {
  const dash = await call<Schemas["DashboardOut"]>("/v1/admin/dashboard");
  if (!dash.ok) return <ApiState result={dash} />;
  const d = dash.data;
  const total = Object.values(d.tenants_by_status).reduce((a, b) => a + b, 0);
  return (
    <>
      <PageHeader title="Platform dashboard" description="Health of the DCS-PIS platform." />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat label="Tenants" value={total} />
        <Stat label="Active" value={d.tenants_by_status.active ?? 0} />
        <Stat label="Users" value={d.users} />
        <Stat label="Failing audit chains" value={d.audit_chains_failing} tone={d.audit_chains_failing > 0 ? "danger" : "ok"} />
      </div>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <Breakdown title="Tenants by status" data={d.tenants_by_status} />
        <Breakdown title="Tenants by region" data={d.tenants_by_region} />
      </div>
      <p className="mt-4 text-xs text-muted-foreground">
        Last audit verification: {d.last_verification_at ? new Date(d.last_verification_at).toUTCString() : "never"}
      </p>
    </>
  );
}

function Stat({ label, value, tone = "ok" }: { label: string; value: number; tone?: "ok" | "danger" }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`mt-1 text-3xl font-semibold ${tone === "danger" ? "text-destructive" : ""}`}>{value}</p>
      </CardContent>
    </Card>
  );
}

function Breakdown({ title, data }: { title: string; data: Record<string, number> }) {
  const entries = Object.entries(data);
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {entries.length === 0 ? (
          <EmptyState title="No tenants yet" className="py-6" />
        ) : (
          <ul className="flex flex-col gap-1 text-sm">
            {entries.map(([k, v]) => (
              <li key={k} className="flex justify-between">
                <span>{k}</span>
                <span className="font-medium">{v}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
