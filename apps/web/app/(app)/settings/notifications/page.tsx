import type { Schemas } from "@dcs/api-client";
import { ForbiddenState, PageHeader } from "@dcs/ui";
import type { Metadata } from "next";

import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { can } from "@/lib/org";

import { PreferencesForm } from "./preferences-form";

export const metadata: Metadata = { title: "Notification preferences" };

// G-06: e-mail / in-app per event type, per organisation.
export default async function NotificationPreferencesPage() {
  const { membership } = await requireContext();
  if (!can(membership, "notifications:read")) return <ForbiddenState />;
  const prefs = await call<Schemas["NotificationPrefsOut"]>("/v1/notification-preferences", { org: membership.org_id });
  if (!prefs.ok) return <ApiState result={prefs} returnTo="/settings/notifications" />;
  return (
    <>
      <PageHeader title="Notifications" description={`How we reach you about ${membership.org_name}.`} />
      <PreferencesForm items={prefs.data.items} labels={prefs.data.event_types} />
    </>
  );
}
