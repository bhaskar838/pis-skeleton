import type { Schemas } from "@dcs/api-client";
import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";

import { SectionPage } from "@/components/section-page";
import { call } from "@/lib/api";

export const metadata: Metadata = { title: "Electricals · integrations & secrets" };

// Electricals: e-mail delivery and every provider API key. Secrets are write-only (ADR-0011 §2).
export default async function ElectricalsPage() {
  const config = await call<Schemas["ConfigOut"]>("/v1/admin/config");
  return (
    <SectionPage
      sectionId="electricals"
      after={config.ok ? <DeploymentValues values={config.data.deployment} /> : null}
      fittings={[
        { label: "LLM provider keys and routing", phase: "P2", detail: "Model Gateway (M-11)" },
        { label: "OAuth apps per connector", phase: "P4", detail: "client IDs and secrets for each SaaS source" },
        { label: "Payment gateway keys", phase: "P8", detail: "billing provider credentials and webhooks" },
      ]}
    />
  );
}

function DeploymentValues({ values }: { values: Schemas["DeploymentValueOut"][] }) {
  return (
    <Card className="mt-6">
      <CardHeader>
        <CardTitle className="text-base">Set by deployment</CardTitle>
        <CardDescription>
          The panel itself depends on these, so they live in the environment or the secrets manager and cannot be
          changed here. Sensitive values are never shown.
        </CardDescription>
      </CardHeader>
      <CardContent>
        <Table>
          <THead>
            <TR>
              <TH>Value</TH>
              <TH>Status</TH>
              <TH>Current</TH>
            </TR>
          </THead>
          <TBody>
            {values.map((v) => (
              <TR key={v.label}>
                <TD>{v.label}</TD>
                <TD>{v.is_set ? <Badge tone="success">Set</Badge> : <Badge tone="warning">Not set</Badge>}</TD>
                <TD className="font-mono text-xs">{v.value ?? (v.is_set ? "hidden" : "—")}</TD>
              </TR>
            ))}
          </TBody>
        </Table>
      </CardContent>
    </Card>
  );
}
