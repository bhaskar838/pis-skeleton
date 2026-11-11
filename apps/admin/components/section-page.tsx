import { Badge, Card, CardContent, CardHeader, CardTitle, PageHeader } from "@dcs/ui";
import type { ReactNode } from "react";

import { ApiState } from "@/components/api-state";
import { SettingsSection } from "@/components/settings-section";
import { SECTION_PATHS } from "@/lib/panel";
import { loadPanel } from "@/lib/panel-server";

export interface Fitting {
  label: string;
  phase: string;
  detail: string;
}

/** One part of the car: its settings, plus the controls later phases will fit to it. */
export async function SectionPage({
  sectionId,
  before,
  after,
  fittings = [],
}: {
  sectionId: string;
  before?: ReactNode;
  after?: ReactNode;
  fittings?: Fitting[];
}) {
  const panel = await loadPanel();
  if (!panel.ok) return <ApiState result={panel.result} />;
  const section = panel.config.sections.find((s) => s.id === sectionId);
  if (!section) return <ApiState result={{ ok: false, status: 404, problem: { type: "about:blank", title: "Unknown section", status: 404 } }} />;
  const path = SECTION_PATHS[sectionId] ?? "/";
  return (
    <>
      <PageHeader title={section.name} description={section.description} />
      {before}
      <SettingsSection section={section} path={path} permissions={panel.permissions} emptyHint={fittings.length ? "The controls below are fitted to this part in later phases." : undefined} />
      {after}
      {fittings.length ? (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="text-base">Fitted in later phases</CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="flex flex-col gap-2 text-sm">
              {fittings.map((f) => (
                <li key={f.label} className="flex flex-wrap items-baseline gap-2">
                  <Badge>{f.phase}</Badge>
                  <span className="font-medium">{f.label}</span>
                  <span className="text-muted-foreground">{f.detail}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      ) : null}
    </>
  );
}
