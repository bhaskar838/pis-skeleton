import { Card, CardContent, CardDescription, CardHeader, CardTitle, Notice } from "@dcs/ui";
import type { Metadata } from "next";
import Link from "next/link";

import { getAccessToken } from "@/lib/session";

import { createOrganisation, startSignUp } from "../actions";
import { OrgForm } from "./org-form";

export const metadata: Metadata = { title: "Create your organisation" };

// A-02: company + country (→ data region), then Keycloak registration; signed-in users create the org directly.
export default async function SignUpPage({ searchParams }: { searchParams: Promise<{ error?: string; new?: string }> }) {
  const params = await searchParams;
  const signedIn = Boolean(await getAccessToken());
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-xl">{signedIn ? "Create an organisation" : "Create your account"}</CardTitle>
        <CardDescription>
          {signedIn
            ? "Your organisation gets its own private database and encryption key."
            : "Tell us about your business, then choose your sign-in details."}
        </CardDescription>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        {params.error ? <Notice tone="danger">{params.error}</Notice> : null}
        {signedIn ? (
          <OrgForm action={createOrganisation} submitLabel="Create organisation" idempotencyKey={crypto.randomUUID()} />
        ) : (
          <OrgForm action={startSignUp} submitLabel="Continue" />
        )}
        {!signedIn ? (
          <p className="text-center text-sm text-muted-foreground">
            Already have an account?{" "}
            <Link href="/auth/sign-in" className="text-primary hover:underline">
              Sign in
            </Link>
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
