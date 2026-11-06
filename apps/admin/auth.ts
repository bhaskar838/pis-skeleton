/**
 * Staff console auth: Keycloak realm `dcs-staff`, every sign-in at acr "mfa" (password + OTP). Staff sessions are
 * shorter than customer sessions: 1 h idle, 12 h absolute (realm settings mirror this).
 */
import { refreshAccessToken, sessionDecision } from "@dcs/auth";
import NextAuth, { type NextAuthConfig } from "next-auth";
import Keycloak from "next-auth/providers/keycloak";

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

const STAFF_IDLE_SECONDS = 60 * 60;
const STAFF_ABSOLUTE_SECONDS = 12 * 60 * 60;

export const authConfig = {
  providers: [Keycloak({ checks: ["pkce", "state"], authorization: { params: { acr_values: "mfa", scope: "openid email profile" } } })],
  session: { strategy: "jwt", maxAge: STAFF_IDLE_SECONDS, updateAge: 5 * 60 },
  pages: { signIn: "/auth/sign-in", error: "/auth/sign-in" },
  trustHost: true,
  callbacks: {
    async jwt({ token, account }) {
      const now = Math.floor(Date.now() / 1000);
      if (account) {
        return { ...token, access_token: account.access_token, refresh_token: account.refresh_token,
          id_token: account.id_token, expires_at: account.expires_at, auth_time: now, error: undefined };
      }
      if (token.auth_time && now - token.auth_time > STAFF_ABSOLUTE_SECONDS) return null;
      switch (sessionDecision(token, now)) {
        case "expired":
          return null;
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
      const issuer = process.env.AUTH_KEYCLOAK_ISSUER;
      if (issuer && url.startsWith(new URL(issuer).origin)) return url;
      if (url.startsWith("/")) return `${baseUrl}${url}`;
      return new URL(url).origin === baseUrl ? url : baseUrl;
    },
  },
} satisfies NextAuthConfig;

export const { handlers, auth, signIn, signOut } = NextAuth(authConfig);
