import type { Metadata } from "next";

import { SystemPage } from "@/components/system-page";

export const metadata: Metadata = { title: "Maintenance" };

export default function Maintenance() {
  return (
    <SystemPage
      title="We'll be right back"
      body="DCS-PIS is undergoing scheduled maintenance. Your data is safe; syncs resume automatically afterwards."
    />
  );
}
