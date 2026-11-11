"use client";

import { Field, Input, Select } from "@dcs/ui";
import { useActionState } from "react";

import type { ActionState } from "@/app/actions";
import { FormMessage, SubmitButton } from "@/components/submit-button";
import type { SignupCountry } from "@/lib/brand";

export function OrgForm({
  action,
  submitLabel,
  countries,
  idempotencyKey,
}: {
  action: (state: ActionState | null, form: FormData) => Promise<ActionState>;
  submitLabel: string;
  countries: SignupCountry[];
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
        hint="Decides where your data is stored. This cannot be changed later. Not listed? We are not available in your country yet."
      >
        <Select id="country" name="country" required defaultValue="" disabled={countries.length === 0}>
          <option value="" disabled>
            {countries.length ? "Choose a country" : "Sign-up is unavailable right now"}
          </option>
          {countries.map((c) => (
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
