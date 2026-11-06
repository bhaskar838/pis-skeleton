"use client";

import type { Org } from "@dcs/api-client";
import { Card, CardContent, Field, Input, Notice, Select } from "@dcs/ui";
import { useActionState } from "react";

import { updateOrgProfile } from "@/app/actions";
import { FormMessage, SubmitButton } from "@/components/submit-button";
import { regionLabel } from "@/lib/org";

const CURRENCIES = ["INR", "GBP", "EUR", "USD", "AED", "SGD", "AUD"];
const TIMEZONES = ["Asia/Kolkata", "Europe/London", "Europe/Dublin", "Europe/Berlin", "Asia/Dubai", "Asia/Singapore", "UTC"];

export function OrgProfileForm({ org, canEdit }: { org: Org; canEdit: boolean }) {
  const [state, action] = useActionState(updateOrgProfile, null);
  const p = org.business_profile as Record<string, string | undefined>;
  return (
    <Card>
      <CardContent className="pt-5">
        {!canEdit ? (
          <div className="mb-4">
            <Notice>You can view this profile. Only owners and admins can change it.</Notice>
          </div>
        ) : null}
        <form action={action} className="grid gap-4 md:grid-cols-2">
          <fieldset disabled={!canEdit} className="contents">
            <Field label="Organisation name" htmlFor="name">
              <Input id="name" name="name" defaultValue={org.name} required maxLength={200} />
            </Field>
            <Field label="Data region" htmlFor="region" hint="Chosen at signup; contact DCS to migrate.">
              <Input id="region" value={regionLabel(org.region)} readOnly disabled />
            </Field>
            <Field label="Industry" htmlFor="industry">
              <Input id="industry" name="industry" defaultValue={p.industry ?? ""} placeholder="e.g. Fitness, D2C retail" />
            </Field>
            <Field label="Business model" htmlFor="business_model">
              <Input id="business_model" name="business_model" defaultValue={p.business_model ?? ""} placeholder="e.g. Memberships" />
            </Field>
            <Field label="Customers" htmlFor="customer_type">
              <Select id="customer_type" name="customer_type" defaultValue={p.customer_type ?? ""}>
                <option value="">Not set</option>
                <option value="B2C">Consumers (B2C)</option>
                <option value="B2B">Businesses (B2B)</option>
                <option value="both">Both</option>
              </Select>
            </Field>
            <Field label="Company size" htmlFor="size_band">
              <Select id="size_band" name="size_band" defaultValue={p.size_band ?? ""}>
                <option value="">Not set</option>
                {["1-10", "11-50", "51-200", "201-1000", "1000+"].map((s) => (
                  <option key={s} value={s}>
                    {s} people
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Currency" htmlFor="currency">
              <Select id="currency" name="currency" defaultValue={p.currency ?? ""}>
                <option value="">Not set</option>
                {CURRENCIES.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Timezone" htmlFor="timezone">
              <Select id="timezone" name="timezone" defaultValue={p.timezone ?? ""}>
                <option value="">Not set</option>
                {TIMEZONES.map((z) => (
                  <option key={z} value={z}>
                    {z}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Fiscal year starts" htmlFor="fiscal_year_start" hint="MM-DD, e.g. 04-01 for April">
              <Input id="fiscal_year_start" name="fiscal_year_start" defaultValue={p.fiscal_year_start ?? ""} placeholder="04-01" />
            </Field>
            <div className="flex items-end justify-end gap-3 md:col-span-2">
              <FormMessage state={state} />
              {canEdit ? <SubmitButton>Save profile</SubmitButton> : null}
            </div>
          </fieldset>
        </form>
      </CardContent>
    </Card>
  );
}
