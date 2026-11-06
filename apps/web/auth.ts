/**
 * Auth.js (next-auth v5) with Keycloak (OIDC Authorization Code + PKCE), SPEC §8.4.
 *
 * Session cookie: httpOnly, SameSite=Lax (Auth.js defaults), 12 h sliding idle (`maxAge`) and a 7 d absolute cap
 * enforced in the jwt callback. Access/refresh tokens live only in the encrypted session JWT cookie and are read
 * server-side (lib/session.ts); they are never placed in the client-visible session object.
 */
import NextAuth, { type NextAuthConfig } from "next-auth";
import Keycloak from "next-auth/providers/keycloak";

import { IDLE_SECONDS, refreshAccessToken, sessionDecision } from "@/lib/auth-policy";

declare module "next-auth/jwt" {
  interface JWT {
    access_token?: string;
    refresh_token?: string;
    id_token?: string;
    expires_at?: number;
    auth_time?: number;
    error?: "RefreshTokenError";
  }
}

declare module "next-auth" {
  interface Session {
    error?: "RefreshTokenError";
  }
}

export const authConfig = {
  providers: [Keycloak({ checks: ["pkce", "state"] })],
  session: { strategy: "jwt", maxAge: IDLE_SECONDS, updateAge: 5 * 60 },
  pages: { signIn: "/auth/sign-in", error: "/auth/sign-in" },
  trustHost: true,
  callbacks: {
    async jwt({ token, account }) {
      const now = Math.floor(Date.now() / 1000);
      if (account) {
        return {
          ...token,
          access_token: account.access_token,
          refresh_token: account.refresh_token,
          id_token: account.id_token,
          expires_at: account.expires_at,
          auth_time: token.auth_time ?? now,
          error: undefined,
        };
      }
      switch (sessionDecision(token, now)) {
        case "expired":
          return null; // absolute lifetime reached: sign out
        case "fresh":
          return token;
        case "broken":
          return { ...token, error: "RefreshTokenError" };
        default:
          return refreshAccessToken(token);
      }
    },
    async session({ session, token }) {
      if (token.error) session.error = token.error;
      return session;
    },
    authorized({ auth }) {
      return Boolean(auth?.user) && !auth?.error;
    },
    redirect({ url, baseUrl }) {
      // Allow Keycloak end-session redirects; everything else must stay on this origin.
      const issuer = process.env.AUTH_KEYCLOAK_ISSUER;
      if (issuer && url.startsWith(new URL(issuer).origin)) return url;
      if (url.startsWith("/")) return `${baseUrl}${url}`;
      return new URL(url).origin === baseUrl ? url : baseUrl;
    },
  },
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
