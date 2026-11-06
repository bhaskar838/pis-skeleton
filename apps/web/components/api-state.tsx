import { Button, EmptyState, ErrorState, ForbiddenState } from "@dcs/ui";
import Link from "next/link";
import { redirect } from "next/navigation";

import { t } from "@/lib/i18n";
import { type ApiResult, outcomeOf, problemMessage } from "@/lib/problem";

/** Render the right page state for a failed API call (forbidden, MFA step-up, not found, error). */
export function ApiState({ result, returnTo = "/" }: { result: ApiResult<unknown>; returnTo?: string }) {
  if (result.ok) return null;
  switch (outcomeOf(result)) {
    case "mfa":
      return redirect(`/auth/mfa?returnTo=${encodeURIComponent(returnTo)}`);
    case "unauthenticated":
      return redirect("/session-expired");
    case "forbidden":
      return <ForbiddenState title={t("state.forbidden.title")} description={t("state.forbidden.body")} />;
    case "not-found":
      return <EmptyState title="Not found" description={problemMessage(result.problem)} />;
    default:
      return (
        <ErrorState
          title={t("state.error.title")}
          description={result.status >= 500 ? t("state.error.body") : problemMessage(result.problem)}
          action={
            <Button asChild variant="outline" size="sm">
              <Link href={returnTo}>{t("state.retry")}</Link>
            </Button>
          }
        />
      );
  }
}
