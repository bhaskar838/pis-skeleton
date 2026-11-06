import { Button, Card, CardContent, CardDescription, CardHeader, CardTitle } from "@dcs/ui";
import type { Metadata } from "next";

import { signIn } from "@/auth";

export const metadata: Metadata = { title: "Staff sign-in" };

export default function StaffSignIn() {
  async function start() {
    "use server";
    await signIn("keycloak", { redirectTo: "/" }, { acr_values: "mfa" });
  }
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-6">
      <Card className="w-full max-w-sm">
        <CardHeader>
          <CardTitle className="text-xl">DCS staff console</CardTitle>
          <CardDescription>Staff SSO with mandatory two-factor authentication. All actions are audited.</CardDescription>
        </CardHeader>
        <CardContent>
          <form action={start}>
            <Button type="submit" className="w-full" size="lg">
              Sign in with staff SSO
            </Button>
          </form>
        </CardContent>
      </Card>
    </main>
  );
}
