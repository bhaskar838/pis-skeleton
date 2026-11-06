"use client";

import type { Schemas } from "@dcs/api-client";
import { Card, CardContent, EmptyState } from "@dcs/ui";
import { useActionState } from "react";

import { savePreferences } from "@/app/actions";
import { FormMessage, SubmitButton } from "@/components/submit-button";

type Pref = Schemas["NotificationPref"];

export function PreferencesForm({ items, labels }: { items: Pref[]; labels: Record<string, string> }) {
  const [state, action] = useActionState(savePreferences, null);
  if (items.length === 0) return <EmptyState title="No notification types yet" />;
  return (
    <Card>
      <CardContent className="pt-5">
        <form action={action}>
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs uppercase tracking-wide text-muted-foreground">
                <th className="pb-2 font-medium">Event</th>
                <th className="pb-2 text-center font-medium">In-app</th>
                <th className="pb-2 text-center font-medium">E-mail</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {items.map((p) => (
                <tr key={p.event_type}>
                  <td className="py-3">
                    <input type="hidden" name="event_type" value={p.event_type} />
                    {labels[p.event_type] ?? p.event_type}
                  </td>
                  <td className="text-center">
                    <input type="checkbox" name={`${p.event_type}:in_app`} defaultChecked={p.in_app} aria-label={`In-app: ${labels[p.event_type]}`} className="h-4 w-4 accent-[var(--color-primary)]" />
                  </td>
                  <td className="text-center">
                    <input type="checkbox" name={`${p.event_type}:email`} defaultChecked={p.email} aria-label={`E-mail: ${labels[p.event_type]}`} className="h-4 w-4 accent-[var(--color-primary)]" />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-4 flex items-center justify-end gap-3">
            <FormMessage state={state} />
            <SubmitButton>Save preferences</SubmitButton>
          </div>
        </form>
      </CardContent>
    </Card>
  );
}
