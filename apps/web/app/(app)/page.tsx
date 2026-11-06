import { Badge, Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Notice, PageHeader } from "@dcs/ui";
import { Activity, BellRing, Lightbulb, Sparkles } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { ProvisioningSteps } from "@/components/shell/live";
import { requireContext } from "@/lib/context";
import { t } from "@/lib/i18n";
import { regionLabel } from "@/lib/org";

export const metadata: Metadata = { title: "Home" };

// H-01 (Phase 0 shell): workspace status, empty pipeline/toolkit/insights panels with their next action.
export default async function HomePage() {
  const { me, membership } = await requireContext();
  const status = membership.org_status;
  const attention: { text: string; href: string }[] = [];
  if (membership.mfa_required && !me.session_mfa) attention.push({ text: "Confirm two-factor authentication", href: "/auth/mfa" });

  return (
    <>
      <PageHeader
        title={`${t("home.title")} · ${membership.org_name}`}
        description={`Data region: ${regionLabel(membership.region)}`}
        actions={<Badge tone={status === "active" ? "success" : status === "failed" ? "danger" : "warning"}>{status}</Badge>}
      />
      {status === "provisioning" ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>{t("home.provisioning")}</CardTitle>
            <CardDescription>{t("home.provisioning.body")}</CardDescription>
          </CardHeader>
          <CardContent>
            <ProvisioningSteps orgId={membership.org_id} realtimeUrl={process.env.NEXT_PUBLIC_REALTIME_URL} />
          </CardContent>
        </Card>
      ) : null}
      {status === "failed" ? (
        <div className="mb-6">
          <Notice tone="danger">
            <strong>{t("home.failed")}.</strong> {t("home.failed.body")}
          </Notice>
        </div>
      ) : null}

      <div className="grid gap-4 md:grid-cols-2">
        <Panel icon={<Activity className="h-4 w-4" />} title={t("home.health")} empty={t("home.health.empty")} />
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <BellRing className="h-4 w-4" aria-hidden /> {t("home.attention")}
            </CardTitle>
          </CardHeader>
          <CardContent>
            {attention.length === 0 ? (
              <p className="text-sm text-muted-foreground">{t("home.attention.empty")}</p>
            ) : (
              <ul className="flex flex-col gap-2">
                {attention.map((a) => (
                  <li key={a.href} className="flex items-center justify-between gap-3 text-sm">
                    <span>{a.text}</span>
                    <Button asChild size="sm" variant="outline">
                      <Link href={a.href}>Open</Link>
                    </Button>
                  </li>
                ))}
              </ul>
            )}
          </CardContent>
        </Card>
        <Panel icon={<Sparkles className="h-4 w-4" />} title={t("home.toolkit")} empty={t("home.toolkit.empty")} />
        <Panel icon={<Lightbulb className="h-4 w-4" />} title={t("home.insights")} empty={t("home.insights.empty")} />
      </div>
    </>
  );
}

function Panel({ icon, title, empty }: { icon: React.ReactNode; title: string; empty: string }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <span aria-hidden>{icon}</span> {title}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-sm text-muted-foreground">{empty}</p>
      </CardContent>
    </Card>
  );
}
