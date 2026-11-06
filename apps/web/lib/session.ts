import "server-only";

import { getToken } from "next-auth/jwt";
import { cookies, headers } from "next/headers";

/** Server-only: read the access token from the encrypted session cookie. Never send it to client components. */
export async function getAccessToken(): Promise<{ accessToken: string; idToken?: string } | null> {
  const h = await headers();
  const secure = (process.env.AUTH_URL ?? "").startsWith("https://");
  const token = await getToken({
    req: { headers: h },
    secret: process.env.AUTH_SECRET ?? "",
    secureCookie: secure,
    salt: secure ? "__Secure-authjs.session-token" : "authjs.session-token",
  });
  if (!token?.access_token || token.error) return null;
  return { accessToken: token.access_token, idToken: token.id_token };
}

export const ORG_COOKIE = "dcs_org";
export const PENDING_ORG_COOKIE = "dcs_pending_org";

export async function getSelectedOrgId(): Promise<string | undefined> {
  return (await cookies()).get(ORG_COOKIE)?.value;
}
