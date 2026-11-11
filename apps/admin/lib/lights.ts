/** Instrument-cluster warning lights (pure, unit-tested). Each light links to the part of the car that fixes it. */
import type { Schemas } from "@dcs/api-client";

export interface Light {
  id: string;
  on: boolean;
  onText: string;
  offText: string;
  href: string;
}

function flag(flags: Schemas["FlagRow"][], key: string): unknown {
  return flags.find((f) => f.key === key && f.scope === "global")?.value;
}

export function warningLights(
  dash: Schemas["DashboardOut"],
  flags: Schemas["FlagRow"][],
  config: Schemas["ConfigOut"] | null,
): Light[] {
  const settings = config?.sections.flatMap((s) => s.settings) ?? [];
  const smtp = settings.find((s) => s.key === "electricals.smtp_host");
  const failed = dash.tenants_by_status.failed ?? 0;
  return [
    {
      id: "audit",
      on: dash.audit_chains_failing > 0,
      onText: `${dash.audit_chains_failing} audit chain(s) failing`,
      offText: "Audit chains OK",
      href: "/security",
    },
    {
      id: "maintenance",
      on: flag(flags, "system.maintenance") === true,
      onText: "Maintenance mode ON",
      offText: "Not in maintenance",
      href: "/settings",
    },
    {
      id: "signup",
      on: flag(flags, "system.signup_enabled") === false,
      onText: "Sign-up switched off",
      offText: "Sign-up open",
      href: "/settings",
    },
    {
      id: "provisioning",
      on: failed > 0,
      onText: `${failed} tenant(s) failed provisioning`,
      offText: "Provisioning OK",
      href: "/tenants?status=failed",
    },
    {
      id: "email",
      on: smtp !== undefined && (smtp.value === "localhost" || smtp.value === ""),
      onText: "E-mail not configured",
      offText: "E-mail configured",
      href: "/electricals",
    },
  ];
}
