"use client";

import { useActionState } from "react";

import { FormMessage, SubmitButton } from "@/components/submit-button";

import { acceptInvite } from "../../actions";

export function AcceptInviteForm({ token }: { token: string }) {
  const [state, action] = useActionState(acceptInvite, null);
  return (
    <form action={action} className="flex flex-col gap-3">
      <input type="hidden" name="token" value={token} />
      <FormMessage state={state} />
      <SubmitButton size="lg" pendingLabel="Joining…">
        Accept invitation
      </SubmitButton>
    </form>
  );
}
