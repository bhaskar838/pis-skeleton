"use client";

/**
 * Live status over WebSocket (SPEC §9.4: no manual refresh). One connection per tab to realtime-gw.
 * The access token is fetched just-in-time from /api/realtime-token and sent as the first message.
 */
import { Bell } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";

export interface LiveEvent {
  type: string;
  [key: string]: unknown;
}

export function useLiveEvents(orgId: string, onEvent: (e: LiveEvent) => void, url?: string) {
  const handler = useRef(onEvent);
  handler.current = onEvent;
  useEffect(() => {
    if (!url || typeof WebSocket === "undefined") return;
    let ws: WebSocket | undefined;
    let closed = false;
    let retry: ReturnType<typeof setTimeout> | undefined;
    const connect = async (attempt: number) => {
      try {
        const resp = await fetch("/api/realtime-token", { cache: "no-store" });
        if (!resp.ok) return;
        const { token } = (await resp.json()) as { token: string };
        ws = new WebSocket(url);
        ws.onopen = () => ws?.send(JSON.stringify({ type: "auth", token, org_id: orgId }));
        ws.onmessage = (msg) => {
          try {
            const event = JSON.parse(String(msg.data)) as LiveEvent;
            if (event.type !== "ping" && event.type !== "ready") handler.current(event);
          } catch {
            /* ignore non-JSON frames (pong) */
          }
        };
        ws.onclose = () => {
          if (!closed) retry = setTimeout(() => void connect(attempt + 1), Math.min(30_000, 1000 * 2 ** attempt));
        };
      } catch {
        if (!closed) retry = setTimeout(() => void connect(attempt + 1), Math.min(30_000, 1000 * 2 ** attempt));
      }
    };
    void connect(0);
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [orgId, url]);
}

export function NotificationBell({ orgId, initialUnread, realtimeUrl }: { orgId: string; initialUnread: number; realtimeUrl?: string }) {
  const [unread, setUnread] = useState(initialUnread);
  const router = useRouter();
  useEffect(() => setUnread(initialUnread), [initialUnread]);
  useLiveEvents(orgId, (e) => {
    if (e.type === "notification.created") {
      setUnread((n) => n + 1);
      router.refresh();
    }
    if (e.type === "tenant.provisioned" || e.type === "provisioning.failed") router.refresh();
  }, realtimeUrl);
  return (
    <Link
      href="/notifications"
      className="relative rounded-md p-2 hover:bg-muted"
      aria-label={unread > 0 ? `Notifications (${unread} unread)` : "Notifications"}
    >
      <Bell className="h-4 w-4" aria-hidden />
      {unread > 0 ? (
        <span className="absolute -right-0.5 -top-0.5 min-w-4 rounded-full bg-primary px-1 text-center text-[10px] font-semibold leading-4 text-primary-foreground">
          {unread > 99 ? "99+" : unread}
        </span>
      ) : null}
    </Link>
  );
}

export function ProvisioningSteps({ orgId, realtimeUrl }: { orgId: string; realtimeUrl?: string }) {
  const [steps, setSteps] = useState<string[]>([]);
  const router = useRouter();
  useLiveEvents(orgId, (e) => {
    if (e.type === "provisioning.step" && typeof e.action === "string") setSteps((s) => [...s, e.action as string]);
    if (e.type === "tenant.provisioned" || e.type === "provisioning.failed") router.refresh();
  }, realtimeUrl);
  // Fallback polling in case the socket is unavailable.
  useEffect(() => {
    const id = setInterval(() => router.refresh(), 5000);
    return () => clearInterval(id);
  }, [router]);
  return (
    <ol className="mt-3 flex flex-col gap-1 text-sm text-muted-foreground" aria-live="polite">
      {steps.map((s, i) => (
        <li key={`${s}-${i}`}>✓ {STEP_LABELS[s] ?? s}</li>
      ))}
    </ol>
  );
}

export const STEP_LABELS: Record<string, string> = {
  "tenant.provision.idp_group_created": "Identity group created",
  "tenant.provision.key_created": "Encryption key created",
  "tenant.provision.database_created": "Private database created",
  "tenant.provision.migrated": "Database structure prepared",
  "tenant.provision.prefixes_created": "Secure storage created",
};
