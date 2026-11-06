import type { Team } from "@dcs/api-client";
import { Badge, Button, Card, CardContent, CardHeader, CardTitle, EmptyState, ForbiddenState, PageHeader, Table, TBody, TD, TH, THead, TR } from "@dcs/ui";
import type { Metadata } from "next";

import { removeMember, revokeInvite } from "@/app/actions";
import { ApiState } from "@/components/api-state";
import { call } from "@/lib/api";
import { requireContext } from "@/lib/context";
import { assignableRoles, can, ROLE_LABELS } from "@/lib/org";

import { InviteForm, RoleSelect } from "./team-forms";

export const metadata: Metadata = { title: "Team & roles" };

// G-02: members, roles, pending invites.
export default async function TeamPage() {
  const { me, membership } = await requireContext();
  if (!can(membership, "members:read")) return <ForbiddenState />;
  const team = await call<Team>(`/v1/orgs/${membership.org_id}/members`, { org: membership.org_id });
  if (!team.ok) return <ApiState result={team} returnTo="/settings/team" />;
  const canInvite = can(membership, "members:invite");
  const canManage = can(membership, "members:manage");
  const grantable = assignableRoles(membership.role);
  const { members, invites } = team.data;

  return (
    <>
      <PageHeader title="Team & roles" description="Invite people and decide what they can see and do." />
      {canInvite ? (
        <Card className="mb-6">
          <CardHeader>
            <CardTitle>Invite someone</CardTitle>
          </CardHeader>
          <CardContent>
            <InviteForm roles={grantable} />
          </CardContent>
        </Card>
      ) : null}

      <h2 className="mb-2 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Members</h2>
      {members.length === 0 ? (
        <EmptyState title="No members yet" description="Invite your first teammate above." />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>Name</TH>
              <TH>E-mail</TH>
              <TH>Role</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {members.map((m) => {
              const self = m.user_id === me.user.id;
              const manageable = canManage && !self && grantable.includes(m.role);
              return (
                <TR key={m.id}>
                  <TD className="font-medium">
                    {m.name ?? "—"} {self ? <Badge>You</Badge> : null}
                  </TD>
                  <TD>{m.email}</TD>
                  <TD>{manageable ? <RoleSelect membershipId={m.id} role={m.role} roles={grantable} /> : ROLE_LABELS[m.role]}</TD>
                  <TD className="text-right">
                    {manageable ? (
                      <form action={removeMember}>
                        <input type="hidden" name="membership_id" value={m.id} />
                        <Button type="submit" variant="ghost" size="sm" className="text-destructive">
                          Remove
                        </Button>
                      </form>
                    ) : null}
                  </TD>
                </TR>
              );
            })}
          </TBody>
        </Table>
      )}

      <h2 className="mb-2 mt-8 text-sm font-semibold uppercase tracking-wide text-muted-foreground">Pending invitations</h2>
      {invites.length === 0 ? (
        <EmptyState title="No pending invitations" description={canInvite ? "Invitations you send appear here until accepted." : undefined} />
      ) : (
        <Table>
          <THead>
            <TR>
              <TH>E-mail</TH>
              <TH>Role</TH>
              <TH>Expires</TH>
              <TH className="text-right">Actions</TH>
            </TR>
          </THead>
          <TBody>
            {invites.map((i) => (
              <TR key={i.id}>
                <TD>{i.email}</TD>
                <TD>{ROLE_LABELS[i.role]}</TD>
                <TD>{new Date(i.expires_at).toLocaleDateString("en-GB")}</TD>
                <TD className="text-right">
                  {canInvite && grantable.includes(i.role) ? (
                    <form action={revokeInvite}>
                      <input type="hidden" name="invite_id" value={i.id} />
                      <Button type="submit" variant="ghost" size="sm">
                        Revoke
                      </Button>
                    </form>
                  ) : null}
                </TD>
              </TR>
            ))}
          </TBody>
        </Table>
      )}
    </>
  );
}
