"use client";

import type { Membership } from "@dcs/api-client";
import { Menu, MenuContent, MenuItem, MenuLabel, MenuSeparator, MenuTrigger } from "@dcs/ui";
import { Check, ChevronsUpDown, Plus } from "lucide-react";
import Link from "next/link";
import { useTransition } from "react";

import { switchOrg } from "@/app/actions";
import { ROLE_LABELS } from "@/lib/org";

export function OrgSwitcher({ memberships, activeOrgId }: { memberships: Membership[]; activeOrgId: string }) {
  const [pending, start] = useTransition();
  const active = memberships.find((m) => m.org_id === activeOrgId);
  return (
    <Menu>
      <MenuTrigger
        className="flex min-w-0 items-center gap-2 rounded-md border border-border px-3 py-1.5 text-sm hover:bg-muted"
        aria-label="Switch organisation"
        disabled={pending}
      >
        <span className="truncate font-medium">{active?.org_name ?? "Select organisation"}</span>
        {active ? <span className="hidden text-xs text-muted-foreground sm:inline">{ROLE_LABELS[active.role]}</span> : null}
        <ChevronsUpDown className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />
      </MenuTrigger>
      <MenuContent align="start">
        <MenuLabel>Organisations</MenuLabel>
        {memberships.map((m) => (
          <MenuItem key={m.org_id} onSelect={() => start(() => switchOrg(m.org_id))}>
            <Check className={m.org_id === activeOrgId ? "h-4 w-4" : "h-4 w-4 opacity-0"} aria-hidden />
            <span className="flex-1 truncate">{m.org_name}</span>
            <span className="text-xs text-muted-foreground">{ROLE_LABELS[m.role]}</span>
          </MenuItem>
        ))}
        <MenuSeparator />
        <MenuItem asChild>
          <Link href="/auth/sign-up?new=1">
            <Plus className="h-4 w-4" aria-hidden /> New organisation
          </Link>
        </MenuItem>
      </MenuContent>
    </Menu>
  );
}
