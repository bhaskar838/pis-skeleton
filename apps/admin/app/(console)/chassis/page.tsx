import type { Schemas } from "@dcs/api-client";
import {
  Badge,
  Button,
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
  EmptyState,
  Input,
  PageHeader,
  Select,
  Table,
  TBody,
  TD,
  TH,
  THead,
  TR,
} from "@dcs/ui";
import type { Metadata } from "next";

import { ApiState } from "@/components/api-state";
import { SettingsSection } from "@/components/settings-section";
import { call } from "@/lib/api";
import { loadPanel } from "@/lib/panel-server";

import { AddRegionForm, CountryForm, RegionStatusForm } from "./region-forms";

export const metadata: Metadata = { title: "Chassis · regions & limits" };

const TONE = { active: "success", planned: "warning", disabled: "neutral" } as const;

// Chassis: the world map (ADR-0012), launch countries (F4) and global limits.
export default async function ChassisPage({ searchParams }: { searchParams: Promise<Record<string, string | undefined>> }) {
  const sp = await searchParams;
  const filters = new URLSearchParams();
  if (sp.region) filters.set("region", sp.region);
  if (sp.enabled === "true" || sp.enabled === "false") filters.set("enabled", sp.enabled);
  if (sp.q) filters.set("q", sp.q.slice(0, 60));
  const [panel, regions, countries] = await Promise.all([
    loadPanel(),
    call<Schemas["RegionOut"][]>("/v1/admin/regions"),
    call<Schemas["CountryOut"][]>(`/v1/admin/countries?${filters.toString()}`),
  ]);
  if (!panel.ok) return <ApiState result={panel.result} />;
  if (!regions.ok) return <ApiState result={regions} />;
  if (!countries.ok) return <ApiState result={countries} />;
  const canEditMap = panel.permissions.has("platform:regions:write");
  const chassis = panel.config.sections.find((s) => s.id === "chassis");
  const regionName = new Map(regions.data.map((r) => [r.code, r.name]));
  return (
    <>
      <PageHeader title="Chassis" description="Where customer data lives, who can sign up, and platform-wide limits." />

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Regions</CardTitle>
          <CardDescription>
            Each tenant lives in one region, chosen from its country at sign-up and never moved. Activate a region only
            after its infrastructure is deployed.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Table>
            <THead>
              <TR>
                <TH>Region</TH>
                <TH>Status</TH>
                <TH className="text-right">Countries</TH>
                <TH className="text-right">Open for sign-up</TH>
                <TH className="text-right">Tenants</TH>
                <TH />
              </TR>
            </THead>
            <TBody>
              {regions.data.map((r) => (
                <TR key={r.code}>
                  <TD>
                    <span className="font-medium">{r.name}</span>{" "}
                    <span className="font-mono text-xs text-muted-foreground">{r.code}</span>
                  </TD>
                  <TD>
                    <Badge tone={TONE[r.status]}>{r.status}</Badge>
                  </TD>
                  <TD className="text-right">{r.countries}</TD>
                  <TD className="text-right">{r.enabled_countries}</TD>
                  <TD className="text-right">{r.live_tenants}</TD>
                  <TD className="text-right">{canEditMap ? <RegionStatusForm region={r} /> : null}</TD>
                </TR>
              ))}
            </TBody>
          </Table>
          {canEditMap ? (
            <div className="mt-4 border-t border-border pt-4">
              <AddRegionForm />
            </div>
          ) : null}
        </CardContent>
      </Card>

      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="text-base">Countries</CardTitle>
          <CardDescription>
            Every country maps to its nearest region. Sign-up opens only for countries switched on here, in an active
            region. Moving a country affects new sign-ups only.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form className="mb-4 flex flex-wrap items-end gap-2" role="search">
            <Input name="q" defaultValue={sp.q ?? ""} placeholder="Search country or code" aria-label="Search countries" className="w-56" />
            <Select name="region" defaultValue={sp.region ?? ""} aria-label="Filter by region" className="w-48">
              <option value="">All regions</option>
              {regions.data.map((r) => (
                <option key={r.code} value={r.code}>
                  {r.name}
                </option>
              ))}
            </Select>
            <Select name="enabled" defaultValue={sp.enabled ?? ""} aria-label="Filter by sign-up" className="w-44">
              <option value="">Any sign-up state</option>
              <option value="true">Open for sign-up</option>
              <option value="false">Closed</option>
            </Select>
            <Button type="submit" variant="outline" size="sm">
              Filter
            </Button>
          </form>
          {countries.data.length === 0 ? (
            <EmptyState title="No countries match" description="Change the search or filters." />
          ) : (
            <Table>
              <THead>
                <TR>
                  <TH>Country</TH>
                  <TH>Region</TH>
                  <TH>Sign-up</TH>
                  {canEditMap ? <TH className="text-right">Change</TH> : null}
                </TR>
              </THead>
              <TBody>
                {countries.data.map((c) => (
                  <TR key={c.code}>
                    <TD>
                      {c.name} <span className="font-mono text-xs text-muted-foreground">{c.code}</span>
                    </TD>
                    <TD className="text-xs">{regionName.get(c.region) ?? c.region}</TD>
                    <TD>{c.signup_enabled ? <Badge tone="success">Open</Badge> : <Badge>Closed</Badge>}</TD>
                    {canEditMap ? (
                      <TD>
                        <CountryForm country={c} regions={regions.data} />
                      </TD>
                    ) : null}
                  </TR>
                ))}
              </TBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {chassis ? (
        <>
          <h2 className="mb-3 text-lg font-semibold">Limits</h2>
          <SettingsSection section={chassis} path="/chassis" permissions={panel.permissions} />
        </>
      ) : null}
    </>
  );
}
