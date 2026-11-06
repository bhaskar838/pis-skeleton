import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Notice } from "@dcs/ui";
import { ShieldCheck } from "lucide-react";
import type { Metadata } from "next";

import { startStepUp } from "../actions";

export const metadata: Metadata = { title: "Two-factor authentication" };

// A-04: MFA enrol & verify. Keycloak shows the TOTP QR code / WebAuthn registration when no factor exists yet,
// otherwise asks for a code. The resulting token carries acr "mfa", which control-api requires for owners/admins.
export default async function MfaPage({ searchParams }: { searchParams: Promise<{ returnTo?: string }> }) {
  const { returnTo } = await searchParams;
  const target = returnTo?.startsWith("/") && !returnTo.startsWith("//") ? returnTo : "/";
  return (
    <Card>
      <CardHeader>
        <div className="mb-2 w-fit rounded-full bg-accent p-2 text-primary">
          <ShieldCheck className="h-5 w-5" aria-hidden />
        </div>
        <CardTitle className="text-xl">Confirm it&apos;s you</CardTitle>
        <CardDescription>
          Your role (Owner or Admin) requires two-factor authentication. Use an authenticator app (TOTP) or a security key.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Notice>
          If you haven&apos;t set up a second factor yet, you&apos;ll scan a QR code with an authenticator app such as Google
          Authenticator, Microsoft Authenticator or 1Password. Keep your recovery options safe.
        </Notice>
        <form action={startStepUp}>
          <input type="hidden" name="returnTo" value={target} />
          <Button type="submit" size="lg" className="w-full">
            Set up or verify two-factor authentication
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
