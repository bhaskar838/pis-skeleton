import type { Metadata } from "next";

import { SectionPage } from "@/components/section-page";

export const metadata: Metadata = { title: "Body · brand & legal" };

// Body: what customers see (product name F6, support contact, legal links). Changes reach the apps within seconds.
export default function BodyPage() {
  return (
    <SectionPage
      sectionId="body"
      fittings={[
        { label: "Logo, colours and e-mail templates", phase: "P9", detail: "branding pass before launch" },
        { label: "Customer-facing locales", phase: "P9", detail: "Hindi and other languages for the web app" },
      ]}
    />
  );
}
