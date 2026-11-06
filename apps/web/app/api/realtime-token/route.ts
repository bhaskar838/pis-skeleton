// Short-lived access token for the realtime WebSocket handshake (browsers cannot set WS headers).
// Same-origin only; the token is the user's own 5-minute access token.
import { NextResponse } from "next/server";

import { getAccessToken } from "@/lib/session";

export async function GET(request: Request) {
  const origin = request.headers.get("origin");
  const expected = process.env.AUTH_URL ?? new URL(request.url).origin;
  if (origin && origin !== new URL(expected).origin) return new NextResponse(null, { status: 403 });
  const session = await getAccessToken();
  if (!session) return new NextResponse(null, { status: 401 });
  return NextResponse.json({ token: session.accessToken }, { headers: { "cache-control": "no-store" } });
}
