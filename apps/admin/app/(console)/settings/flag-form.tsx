"use client";

import { Field, Input, Select } from "@dcs/ui";
import { useActionState } from "react";

import { upsertFlag } from "@/app/actions";
import { FormMessage, SubmitButton } from "@/components/form-bits";

export function FlagForm() {
  const [state, action] = useActionState(upsertFlag, null);
  return (
    <form action={action} className="grid items-end gap-3 md:grid-cols-[1fr_140px_1fr_1fr_auto]">
      <Field label="Key" htmlFor="flag-key">
        <Input id="flag-key" name="key" placeholder="ui.insights_feed" required />
      </Field>
      <Field label="Scope" htmlFor="flag-scope">
        <Select id="flag-scope" name="scope" defaultValue="global">
          <option value="global">global</option>
          <option value="plan">plan</option>
          <option value="org">org</option>
        </Select>
      </Field>
      <Field label="Scope id" htmlFor="flag-scope-id" hint="Plan id or org UUID; empty for global">
        <Input id="flag-scope-id" name="scope_id" />
      </Field>
      <Field label="Value (JSON)" htmlFor="flag-value">
        <Input id="flag-value" name="value" placeholder="true" required />
      </Field>
      <SubmitButton>Save</SubmitButton>
      <div className="md:col-span-5">
        <FormMessage state={state} />
      </div>
    </form>
  );
}
