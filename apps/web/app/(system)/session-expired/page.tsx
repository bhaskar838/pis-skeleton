import { Button } from "@dcs/ui";
import type { Metadata } from "next";

import { startSignIn } from "@/app/auth/actions";
import { SystemPage } from "@/components/system-page";

export const metadata: Metadata = { title: "Session expired" };

export default function SessionExpired() {
  return (
    <SystemPage
      title="Your session has expired"
      body="For your security you were signed out after a period of inactivity. Sign in again to continue."
      action={
        <form action={startSignIn}>
          <input type="hidden" name="returnTo" value="/" />
          <Button type="submit">Sign in again</Button>
        </form>
      }
    />
  );
}
