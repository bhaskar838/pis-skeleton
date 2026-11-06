import { type ApiResult, outcomeOf, problemMessage } from "@dcs/api-client";
import { EmptyState, ErrorState, ForbiddenState } from "@dcs/ui";
import { redirect } from "next/navigation";

export function ApiState({ result }: { result: ApiResult<unknown> }) {
  if (result.ok) return null;
  switch (outcomeOf(result)) {
    case "unauthenticated":
    case "mfa":
      return redirect("/auth/sign-in");
    case "forbidden":
      return <ForbiddenState description="Your staff role doesn't include this permission." />;
    case "not-found":
      return <EmptyState title="Not found" description={problemMessage(result.problem)} />;
    default:
      return <ErrorState description={problemMessage(result.problem)} />;
  }
}
