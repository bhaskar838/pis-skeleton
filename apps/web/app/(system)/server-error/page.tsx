import type { Metadata } from "next";

import { SystemPage } from "@/components/system-page";

export const metadata: Metadata = { title: "Server error" };

export default function ServerError() {
  return (
    <SystemPage code="500" title="Something went wrong" body="An unexpected error occurred. Our team has been notified." />
  );
}
