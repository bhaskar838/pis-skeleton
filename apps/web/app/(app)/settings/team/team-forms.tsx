"use client";

import type { CustomerRole } from "@dcs/api-client";
import { Field, Input, Select } from "@dcs/ui";
import { useActionState, useRef } from "react";

import { changeRole, inviteMember } from "@/app/actions";
import { FormMessage, SubmitButton } from "@/components/submit-button";
import { ROLE_LABELS } from "@/lib/org";

export function InviteForm({ roles }: { roles: CustomerRole[] }) {
  const [state, action] = useActionState(inviteMember, null);
  return (
    <form action={action} className="grid items-end gap-3 md:grid-cols-[1fr_200px_auto]">
      <Field label="E-mail address" htmlFor="invite-email">
        <Input id="invite-email" name="email" type="email" required placeholder="analyst@company.com" />
      </Field>
      <Field label="Role" htmlFor="invite-role">
        <Select id="invite-role" name="role" defaultValue={roles.includes("analyst") ? "analyst" : roles[0]}>
          {roles.map((r) => (
            <option key={r} value={r}>
              {ROLE_LABELS[r]}
            </option>
          ))}
        </Select>
      </Field>
      <SubmitButton pendingLabel="Sending…">Send invitation</SubmitButton>
      <div className="md:col-span-3">
        <FormMessage state={state} />
      </div>
    </form>
  );
}

export function RoleSelect({ membershipId, role, roles }: { membershipId: string; role: CustomerRole; roles: CustomerRole[] }) {
  const [state, action] = useActionState(changeRole, null);
  const formRef = useRef<HTMLFormElement>(null);
  return (
    <form ref={formRef} action={action} className="flex items-center gap-2">
      <input type="hidden" name="membership_id" value={membershipId} />
      <Select
        name="role"
        aria-label="Role"
        defaultValue={role}
        className="h-8 w-40"
        onChange={() => formRef.current?.requestSubmit()}
      >
        {roles.map((r) => (
          <option key={r} value={r}>
            {ROLE_LABELS[r]}
          </option>
        ))}
      </Select>
      {state?.error ? <span className="text-xs text-destructive">{state.error}</span> : null}
    </form>
  );
}
