import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

export const metadata: Metadata = { title: "Reset password" };
// Reads the Keycloak URL at request time (runtime env), never at build time.
export const dynamic = "force-dynamic";

// A-03: Keycloak runs the reset flow (e-mail link, password policy); this page hands over to it.
export default function ResetPage() {
  const issuer = process.env.AUTH_KEYCLOAK_ISSUER ?? "";
  const clientId = process.env.AUTH_KEYCLOAK_ID ?? "dcs-web";
  const resetUrl = `${issuer}/login-actions/reset-credentials?client_id=${encodeURIComponent(clientId)}`;
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">Forgot your password?</CardTitle>
        <CardDescription>
          We&apos;ll e-mail you a secure link to choose a new password. The link expires after a short time.
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <Button asChild size="lg">
          <a href={resetUrl}>Send reset link</a>
        </Button>
        <Link href="/auth/sign-in" className="text-center text-sm text-primary hover:underline">
          Back to sign in
        </Link>
      </CardContent>
    </Card>
  );
}
