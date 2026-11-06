"use client";

import { Field, Input, Select } from "@dcs/ui";
import { useActionState } from "react";

import type { ActionState } from "@/app/actions";
import { FormMessage, SubmitButton } from "@/components/submit-button";
import { COUNTRIES } from "@/lib/org";

export function OrgForm({
  action,
  submitLabel,
  idempotencyKey,
}: {
  action: (state: ActionState | null, form: FormData) => Promise<ActionState>;
  submitLabel: string;
  idempotencyKey?: string;
}) {
  const [state, formAction] = useActionState(action, null);
  return (
    <form action={formAction} className="flex flex-col gap-4">
      {idempotencyKey ? <input type="hidden" name="idempotency_key" value={idempotencyKey} /> : null}
      <Field label="Company name" htmlFor="name">
        <Input id="name" name="name" required maxLength={200} autoComplete="organization" placeholder="Northwind Fitness" />
      </Field>
      <Field
        label="Country"
        htmlFor="country"
        hint="Decides where your data is stored (India or UK/EU). This cannot be changed later."
      >
        <Select id="country" name="country" required defaultValue="">
          <option value="" disabled>
            Choose a country
          </option>
          {COUNTRIES.map((c) => (
            <option key={c.code} value={c.code}>
              {c.name}
            </option>
          ))}
        </Select>
      </Field>
      <FormMessage state={state} />
      <SubmitButton size="lg" pendingLabel="Working…">
        {submitLabel}
      </SubmitButton>
    </form>
  );
}
