import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle, Notice } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { startSignIn } from "../actions";

export const metadata: Metadata = { title: "Sign in" };

// A-01: the credential form itself is Keycloak's (Keycloakify-themed); this page starts the OIDC + PKCE flow.
export default async function SignInPage({
  searchParams,
}: {
  searchParams: Promise<{ callbackUrl?: string; signed_out?: string; error?: string }>;
}) {
  const params = await searchParams;
  const returnTo = params.callbackUrl?.startsWith("/") ? params.callbackUrl : "/";
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Sign in</CardTitle>
        <CardDescription>Use your DCS-PIS account. Owners and admins confirm with a second factor.</CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {params.signed_out ? <Notice tone="success">You have been signed out.</Notice> : null}
        {params.error ? <Notice tone="danger">Sign-in failed. Please try again.</Notice> : null}
        <form action={startSignIn}>
          <input type="hidden" name="returnTo" value={returnTo} />
          <Button type="submit" className="w-full" size="lg">
            Continue to sign in
          </Button>
        </form>
        <div className="flex justify-between text-sm">
          <Link href="/auth/reset" className="text-primary hover:underline">
            Forgot password?
          </Link>
          <Link href="/auth/sign-up" className="text-primary hover:underline">
            Create an account
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
