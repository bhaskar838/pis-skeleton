import type { Org } from "@dcs/api-client";
import { ForbiddenState, PageHeader } from "@dcs/ui";
import type { Metadata } from "next";

import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { can } from "@/lib/org";

import { OrgProfileForm } from "./profile-form";

export const metadata: Metadata = { title: "Organisation" };

// G-01: organisation profile. Region is fixed at signup (data residency) and shown read-only.
export default async function OrgSettingsPage() {
  const { membership } = await requireContext();
  if (!can(membership, "org:read")) return <ForbiddenState />;
  const org = await call<Org>(`/v1/orgs/${membership.org_id}`, { org: membership.org_id });
  if (!org.ok) return <ApiState result={org} returnTo="/settings/org" />;
  return (
    <>
      <PageHeader title="Organisation" description="Business profile used to tailor your toolkit." />
      <OrgProfileForm org={org.data} canEdit={can(membership, "org:write")} />
    </>
  );
}
