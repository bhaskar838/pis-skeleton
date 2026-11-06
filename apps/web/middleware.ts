// Every app navigation passes through Auth.js: refreshes the access token before it expires and sends
// unauthenticated users to /auth/sign-in. Public routes are excluded by the matcher.
export { auth as middleware } from "@/auth";

export const config = {
  matcher: [
    "/((?!api/auth|auth/|_next/static|_next/image|favicon|forbidden|maintenance|session-expired|server-error).*)",
  ],
};
