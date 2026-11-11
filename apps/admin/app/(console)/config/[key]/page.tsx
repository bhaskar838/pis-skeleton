import type { Schemas } from "@dcs/api-client";
import { Badge, EmptyState, PageHeader, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { revertSetting } from "@/app/(console)/panel-actions";
import { ApiState } from "@/components/api-state";
import { SubmitButton } from "@/components/form-bits";
import { call } from "@/lib/api";
import { displayValue, SECTION_PATHS } from "@/lib/panel";
import { loadPanel } from "@/lib/panel-server";

export const metadata: Metadata = { title: "Setting history" };

const ACTION_LABEL: Record<string, string> = {
  set: "Changed",
  revert: "Reverted",
  reset: "Reset to default",
  secret_set: "Secret stored",
  secret_cleared: "Secret cleared",
};

// Every change to one setting, newest first, with one-click revert (ADR-0011 §1).
export default async function SettingHistoryPage({ params }: { params: Promise<{ key: string }> }) {
  const { key } = await params;
  const safeKey = /^[a-z_]+\.[a-z0-9_.]+$/.test(key) ? key : "invalid";
  const [panel, history] = await Promise.all([
    loadPanel(),
    call<Schemas["SettingHistoryOut"][]>(`/v1/admin/config/${safeKey}/history`),
  ]);
  if (!panel.ok) return <ApiState result={panel.result} />;
  if (!history.ok) return <ApiState result={history} />;
  const setting = panel.config.sections.flatMap((s) => s.settings).find((s) => s.key === safeKey);
  if (!setting) return <EmptyState title="Unknown setting" />;
  const writable = panel.permissions.has(setting.write_permission);
  const back = SECTION_PATHS[setting.section] ?? "/";
  return (
    <>
      <PageHeader
        title={`${setting.label}: history`}
        description={`${setting.key} · current: ${setting.type === "secret" ? (setting.is_set ? "set" : "not set") : displayValue(setting.value)}`}
      />
      <p className="mb-4 text-sm">
        <Link href={back} className="underline">
          Back to the section
        </Link>
      </p>
      {history.data.length === 0 ? (
        <EmptyState title="Never changed in the panel" description="The deployment value or the default applies." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Version</TH>
              <TH>Change</TH>
              <TH>Value</TH>
              <TH>By</TH>
              <TH>When (UTC)</TH>
              <TH />
            </TR>
          </THead>
          <TBody>
            {history.data.map((h) => (
              <TR key={h.version}>
                <TD>v{h.version}</TD>
                <TD>
                  <Badge>{ACTION_LABEL[h.action] ?? h.action}</Badge>
                </TD>
                <TD className="font-mono text-xs">{setting.type === "secret" ? "hidden" : displayValue(h.value)}</TD>
                <TD className="text-xs">{h.changed_by}</TD>
                <TD className="text-xs">{new Date(h.changed_at).toUTCString()}</TD>
                <TD className="text-right">
                  {writable && setting.type !== "secret" && (h.action === "set" || h.action === "revert") ? (
                    <form action={revertSetting}>
                      <input type="hidden" name="key" value={setting.key} />
                      <input type="hidden" name="version" value={h.version} />
                      <SubmitButton size="sm" variant="ghost">
                        Go back to this
                      </SubmitButton>
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
