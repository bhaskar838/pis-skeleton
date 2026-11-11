import type { Schemas } from "@dcs/api-client";
import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, ErrorState, Notice } from "@dcs/ui";
import type { Metadata } from "next";

import { call } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/org";
import { problemMessage } from "@/lib/problem";
import { getAccessToken } from "@/lib/session";
import { getBrand } from "@/lib/brand";

import { startSignIn } from "../../actions";
import { AcceptInviteForm } from "./accept-form";

export const metadata: Metadata = { title: "Accept invitation" };

// A-05: public invite preview; accepting requires signing in with the invited e-mail address.
export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const preview = await call<Schemas["InvitePreview"]>(`/v1/invites/${encodeURIComponent(token)}`, { auth: false, org: false });
  if (!preview.ok) {
    return <ErrorState title="This invitation isn't valid" description={problemMessage(preview.problem)} />;
  }
  const invite = preview.data;
  const [signedIn, brand] = await Promise.all([getAccessToken().then(Boolean), getBrand()]);
  const returnTo = `/auth/invite/${token}`;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Join {invite.org_name}</CardTitle>
        <CardDescription>
          You&apos;ve been invited as <strong>{ROLE_LABELS[invite.role]}</strong>. The invitation was sent to {invite.email_hint}.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {invite.status === "expired" ? (
          <Notice tone="warning">This invitation has expired. Ask the person who invited you to send a new one.</Notice>
        ) : signedIn ? (
          <AcceptInviteForm token={token} />
        ) : (
          <div className="flex flex-col gap-2">
            <form action={startSignIn}>
              <input type="hidden" name="returnTo" value={returnTo} />
              <Button type="submit" className="w-full" size="lg">
                Sign in to accept
              </Button>
            </form>
            <p className="text-center text-sm text-muted-foreground">
              New to {brand.product_name}? Choose &ldquo;Register&rdquo; on the sign-in page using the invited e-mail address.
            </p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
