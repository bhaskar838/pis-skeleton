import type { Schemas } from "@dcs/api-client";
import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState, ForbiddenState, PageHeader } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { can, ROLE_LABELS } from "@/lib/org";

export const metadata: Metadata = { title: "Security" };

// G-03: MFA policy, current session, account security; API keys / IP allowlist arrive later.
export default async function SecurityPage() {
  const { membership } = await requireContext();
  if (!can(membership, "security:read")) return <ForbiddenState />;
  const summary = await call<Schemas["SecuritySummary"]>("/v1/security/summary", { org: membership.org_id });
  if (!summary.ok) return <ApiState result={summary} returnTo="/settings/security" />;
  const s = summary.data;
  return (
    <>
      <PageHeader title="Security" description="How people sign in to your organisation." />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Two-factor authentication policy</CardTitle>
            <CardDescription>Required for these roles on every session:</CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {s.mfa_required_roles.map((r) => (
              <Badge key={r} tone="primary">
                {ROLE_LABELS[r as keyof typeof ROLE_LABELS] ?? r}
              </Badge>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>This session</CardTitle>
            <CardDescription>
              {s.session_mfa ? "Signed in with a second factor." : "Signed in with a password only."}
            </CardDescription>
          </CardHeader>
          <CardContent className="flex flex-wrap items-center gap-3">
            <Badge tone={s.session_mfa ? "success" : "warning"}>{s.session_mfa ? "MFA verified" : "No MFA"}</Badge>
            <Button asChild size="sm" variant="outline">
              <a href={s.account_console_url} target="_blank" rel="noreferrer">
                Manage sign-in methods & sessions
              </a>
            </Button>
            {!s.session_mfa ? (
              <Button asChild size="sm">
                <Link href="/auth/mfa?returnTo=/settings/security">Set up two-factor</Link>
              </Button>
            ) : null}
          </CardContent>
        </Card>
      </div>
      <h2 className="mb-2 mt-8 text-sm font-semibold uppercase tracking-wide text-muted-foreground">API keys</h2>
      <EmptyState title="No API keys" description="Programmatic access with scoped API keys is coming in a later release." />
      <h2 className="mb-2 mt-8 text-sm font-semibold uppercase tracking-wide text-muted-foreground">IP allowlist</h2>
      <EmptyState title="Not configured" description="Restricting sign-in to your office IP ranges is available on the enterprise plan." />
    </>
  );
}
