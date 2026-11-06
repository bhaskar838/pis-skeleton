import type { Metadata } from "next";

import { SystemPage } from "@/components/system-page";

export const metadata: Metadata = { title: "Access denied" };

export default function Forbidden() {
  return (
    <SystemPage
      code="403"
      title="Access denied"
      body="Your role doesn't allow this action. Ask an owner or admin of your organisation for access."
    />
  );
}
