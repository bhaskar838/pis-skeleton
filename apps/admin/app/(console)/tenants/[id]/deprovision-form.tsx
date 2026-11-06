"use client";

import { Field, Input, Notice } from "@dcs/ui";
import { useActionState } from "react";

import { deprovisionTenant } from "@/app/actions";
import { FormMessage, SubmitButton } from "@/components/form-bits";

export function DeprovisionForm({ orgId, slug }: { orgId: string; slug: string }) {
  const [state, action] = useActionState(deprovisionTenant, null);
  return (
    <form action={action} className="flex flex-col gap-4">
      <Notice tone="danger">
        Drops the tenant database and roles, deletes (or lifecycle-tags) storage prefixes and schedules the encryption key
        for deletion (crypto-shred). The audit trail is kept. This cannot be undone after the waiting period.
      </Notice>
      <input type="hidden" name="org_id" value={orgId} />
      <Field label={`Type ${slug} to confirm`} htmlFor="confirm_slug">
        <Input id="confirm_slug" name="confirm_slug" autoComplete="off" required />
      </Field>
      <Field label="Reason" htmlFor="reason">
        <Input id="reason" name="reason" required minLength={3} maxLength={500} />
      </Field>
      <Field label="Key deletion waiting period (days)" htmlFor="pending_days" hint="7-30 days (default 30)">
        <Input id="pending_days" name="pending_days" type="number" min={7} max={30} defaultValue={30} required />
      </Field>
      <FormMessage state={state} />
      <SubmitButton variant="destructive">Deprovision tenant</SubmitButton>
    </form>
  );
}
