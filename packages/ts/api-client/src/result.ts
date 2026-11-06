import { isProblem, type Problem, problemSlug } from "./index";

export type ApiResult<T> = { ok: true; data: T; status: number } | { ok: false; status: number; problem: Problem };

export type PageOutcome = "ok" | "forbidden" | "mfa" | "unauthenticated" | "not-found" | "not-ready" | "error";

/** Map an API failure to the page state the UI must show (SPEC §0.3: loading/empty/error/forbidden states). */
export function outcomeOf(result: ApiResult<unknown>): PageOutcome {
  if (result.ok) return "ok";
  const slug = problemSlug(result.problem);
  if (result.status === 401) return "unauthenticated";
  if (slug === "mfa-required") return "mfa";
  if (result.status === 403) return "forbidden";
  if (result.status === 404) return "not-found";
  if (slug === "tenant-not-ready") return "not-ready";
  return "error";
}

export function toProblem(status: number, body: unknown): Problem {
  if (isProblem(body)) return body;
  return { type: "about:blank", title: status >= 500 ? "Server error" : "Request failed", status };
}

/** First human-readable message of a problem, including field validation errors. */
export function problemMessage(problem: Problem): string {
  if (problem.errors?.length) {
    return problem.errors.map((e) => `${e.loc.filter((l) => l !== "body").join(".")}: ${e.msg}`).join("; ");
  }
  return problem.detail ?? problem.title;
}
