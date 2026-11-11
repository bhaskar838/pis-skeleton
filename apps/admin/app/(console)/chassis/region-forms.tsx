"use client";

import type { Schemas } from "@dcs/api-client";
import { Field, Input, Select } from "@dcs/ui";
import { useActionState } from "react";

import { createRegion, updateCountry, updateRegion } from "@/app/(console)/panel-actions";
import { FormMessage, SubmitButton } from "@/components/form-bits";

const NEXT: Record<string, { status: string; label: string }[]> = {
  active: [{ status: "planned", label: "Switch off" }],
  planned: [
    { status: "active", label: "Activate" },
    { status: "disabled", label: "Disable" },
  ],
  disabled: [{ status: "planned", label: "Mark planned" }],
};

export function RegionStatusForm({ region }: { region: Schemas["RegionOut"] }) {
  const [state, action] = useActionState(updateRegion, null);
  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex gap-1">
        {(NEXT[region.status] ?? []).map((n) => (
          <form key={n.status} action={action}>
            <input type="hidden" name="code" value={region.code} />
            <input type="hidden" name="status" value={n.status} />
            <SubmitButton size="sm" variant={n.status === "active" ? "default" : "ghost"}>
              {n.label}
            </SubmitButton>
          </form>
        ))}
      </div>
      <FormMessage state={state} />
    </div>
  );
}

export function AddRegionForm() {
  const [state, action] = useActionState(createRegion, null);
  return (
    <form action={action} className="grid items-end gap-3 md:grid-cols-[180px_1fr_100px_auto]">
      <Field label="AWS region code" htmlFor="region-code">
        <Input id="region-code" name="code" placeholder="sa-east-1" required />
      </Field>
      <Field label="Name" htmlFor="region-name">
        <Input id="region-name" name="name" placeholder="São Paulo" required />
      </Field>
      <Field label="Order" htmlFor="region-sort">
        <Input id="region-sort" name="sort" type="number" defaultValue="100" />
      </Field>
      <SubmitButton>Add region</SubmitButton>
      <div className="md:col-span-4">
        <FormMessage state={state} />
      </div>
    </form>
  );
}

export function CountryForm({ country, regions }: { country: Schemas["CountryOut"]; regions: Schemas["RegionOut"][] }) {
  const [state, action] = useActionState(updateCountry, null);
  return (
    <form action={action} className="flex flex-wrap items-center justify-end gap-2">
      <input type="hidden" name="code" value={country.code} />
      <Select name="region" defaultValue={country.region} aria-label={`${country.name} region`} className="h-8 w-48 text-xs">
        {regions.map((r) => (
          <option key={r.code} value={r.code}>
            {r.name} ({r.code}){r.status === "active" ? "" : ` · ${r.status}`}
          </option>
        ))}
      </Select>
      <label className="flex items-center gap-1 text-xs">
        <input type="checkbox" name="signup_enabled" defaultChecked={country.signup_enabled} aria-label={`${country.name} open for sign-up`} />
        Sign-up
      </label>
      <SubmitButton size="sm" variant="ghost">
        Save
      </SubmitButton>
      <FormMessage state={state} />
    </form>
  );
}
