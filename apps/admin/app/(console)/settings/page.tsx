import type { Schemas } from "@dcs/api-client";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, PageHeader, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";

import { deleteFlag, setMaintenance } from "@/app/actions";
import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";

import { FlagForm } from "./flag-form";

export const metadata: Metadata = { title: "Settings & flags" };

// M-13: feature flags per global / plan / org, maintenance mode.
export default async function SettingsPage() {
  const [flags, me] = await Promise.all([
    call<Schemas["FlagRow"][]>("/v1/admin/flags"),
    call<Schemas["StaffMeOut"]>("/v1/admin/me"),
  ]);
  if (!flags.ok) return <ApiState result={flags} />;
  const canWrite = me.ok && me.data.permissions.includes("platform:flags:write");
  const maintenance = flags.data.find((f) => f.key === "system.maintenance" && f.scope === "global")?.value === true;
  return (
    <>
      <PageHeader title="Settings & feature flags" description="Org overrides beat plan overrides, which beat global values." />
      <Card className="mb-6">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            Maintenance mode <Badge tone={maintenance ? "danger" : "success"}>{maintenance ? "ON" : "off"}</Badge>
          </CardTitle>
        </CardHeader>
        <CardContent>
          {canWrite ? (
            <form action={setMaintenance}>
              <input type="hidden" name="on" value={maintenance ? "false" : "true"} />
              <Button type="submit" variant={maintenance ? "default" : "destructive"}>
                {maintenance ? "Turn maintenance off" : "Turn maintenance on"}
              </Button>
            </form>
          ) : (
            <p className="text-sm text-muted-foreground">Your role can view but not change settings.</p>
          )}
        </CardContent>
      </Card>
      {canWrite ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Set a flag</CardTitle>
          </CardHeader>
          <CardContent>
            <FlagForm />
          </CardContent>
        </Card>
      ) : null}
      {flags.data.length === 0 ? (
        <EmptyState title="No overrides" description="Code defaults apply everywhere." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Key</TH>
              <TH>Scope</TH>
              <TH>Value</TH>
              <TH>Updated</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {flags.data.map((f) => (
              <TR key={`${f.key}@${f.scope}:${f.scope_id}`}>
                <TD className="font-mono text-xs">{f.key}</TD>
                <TD className="text-xs">
                  {f.scope}
                  {f.scope_id ? `: ${f.scope_id}` : ""}
                </TD>
                <TD className="font-mono text-xs">{JSON.stringify(f.value)}</TD>
                <TD className="text-xs">{f.updated_at.slice(0, 10)}</TD>
                <TD className="text-right">
                  {canWrite ? (
                    <form action={deleteFlag}>
                      <input type="hidden" name="key" value={f.key} />
                      <input type="hidden" name="scope" value={f.scope} />
                      <input type="hidden" name="scope_id" value={f.scope_id} />
                      <Button type="submit" variant="ghost" size="sm">
                        Remove
                      </Button>
                    </form>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </>
  );
}
