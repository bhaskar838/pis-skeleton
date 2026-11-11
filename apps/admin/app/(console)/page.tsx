import type { Schemas } from "@dcs/api-client";
import { Card, CardContent, CardHeader, CardTitle, EmptyState, PageHeader } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";
import { type Light, warningLights } from "@/lib/lights";

export const metadata: Metadata = { title: "Instrument cluster" };

// M-01 as the car's instrument cluster: gauges for the platform and warning lights that link to the part to fix.
// Queue depth, LLM spend and sandbox use join the cluster as their phases arrive.
export default async function Dashboard() {
  const [dash, flags, config] = await Promise.all([
    call<Schemas["DashboardOut"]>("/v1/admin/dashboard"),
    call<Schemas["FlagRow"][]>("/v1/admin/flags"),
    call<Schemas["ConfigOut"]>("/v1/admin/config"),
  ]);
  if (!dash.ok) return <ApiState result={dash} />;
  const d = dash.data;
  const total = Object.values(d.tenants_by_status).reduce((a, b) => a + b, 0);
  const lights = warningLights(d, flags.ok ? flags.data : [], config.ok ? config.data : null);
  return (
    <>
      <PageHeader title="Instrument cluster" description="Gauges and warning lights for the whole platform." />
      <WarningLights lights={lights} />
      <div className="mt-4 grid gap-4 md:grid-cols-4">
        <Gauge label="Tenants" value={total} />
        <Gauge label="Active" value={d.tenants_by_status.active ?? 0} />
        <Gauge label="Users" value={d.users} />
        <Gauge label="Failing audit chains" value={d.audit_chains_failing} tone={d.audit_chains_failing > 0 ? "danger" : "ok"} />
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

function WarningLights({ lights }: { lights: Light[] }) {
  return (
    <section aria-label="Warning lights" className="flex flex-wrap gap-2">
      {lights.map((l) => (
        <Link
          key={l.id}
          href={l.href}
          className={`flex items-center gap-2 rounded-full border px-3 py-1 text-xs ${
            l.on ? "border-destructive/40 bg-destructive/10 text-destructive" : "border-border text-muted-foreground"
          }`}
        >
          <span aria-hidden="true" className={`inline-block size-2 rounded-full ${l.on ? "bg-destructive" : "bg-success"}`} />
          <span>{l.on ? l.onText : l.offText}</span>
        </Link>
      ))}
    </section>
  );
}

function Gauge({ label, value, tone = "ok" }: { label: string; value: number; tone?: "ok" | "danger" }) {
  return (
    <Card>
      <CardContent className="pt-5">
        <p className="text-xs uppercase tracking-wide text-muted-foreground">{label}</p>
        <p className={`mt-1 text-3xl font-semibold tabular-nums ${tone === "danger" ? "text-destructive" : ""}`}>{value}</p>
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
