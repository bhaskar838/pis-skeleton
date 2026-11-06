/** Session lifetime policy (SPEC §8.4): 12 h idle (Auth.js maxAge), 7 d absolute, token refresh. Pure + testable. */
/** The token fields the policy reads/writes (a subset of the Auth.js JWT). */
export interface SessionToken {
  access_token?: string;
  refresh_token?: string;
  id_token?: string;
  expires_at?: number;
  auth_time?: number;
  error?: "RefreshTokenError";
  [key: string]: unknown;
}

export const IDLE_SECONDS = 12 * 60 * 60;
export const ABSOLUTE_SECONDS = 7 * 24 * 60 * 60;
const REFRESH_MARGIN_SECONDS = 60;

export async function refreshAccessToken<T extends SessionToken>(
  token: T,
  fetchImpl: typeof fetch = fetch,
): Promise<T & SessionToken> {
  const issuer = process.env.AUTH_KEYCLOAK_ISSUER ?? "";
  try {
    const resp = await fetchImpl(`${issuer}/protocol/openid-connect/token`, {
      method: "POST",
      headers: { "content-type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token",
        refresh_token: token.refresh_token ?? "",
        client_id: process.env.AUTH_KEYCLOAK_ID ?? "",
        client_secret: process.env.AUTH_KEYCLOAK_SECRET ?? "",
      }),
    });
    const body = (await resp.json()) as { access_token?: string; refresh_token?: string; id_token?: string; expires_in?: number };
    if (!resp.ok || !body.access_token) return { ...token, error: "RefreshTokenError" };
    return {
      ...token,
      access_token: body.access_token,
      refresh_token: body.refresh_token ?? token.refresh_token,
      id_token: body.id_token ?? token.id_token,
      expires_at: Math.floor(Date.now() / 1000) + (body.expires_in ?? 300),
      error: undefined,
    };
  } catch {
    return { ...token, error: "RefreshTokenError" };
  }
}

/** Pure session-lifetime policy, unit-tested in lib/auth-policy.test.ts. */
export function sessionDecision(token: SessionToken, nowSeconds: number): "expired" | "fresh" | "refresh" | "broken" {
  if (token.auth_time && nowSeconds - token.auth_time > ABSOLUTE_SECONDS) return "expired";
  if (token.expires_at && nowSeconds < token.expires_at - REFRESH_MARGIN_SECONDS) return "fresh";
  if (!token.refresh_token) return "broken";
  return "refresh";
}
