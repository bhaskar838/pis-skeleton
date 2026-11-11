import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@dcs/ui";
import type { Metadata } from "next";

import { SectionPage } from "@/components/section-page";

export const metadata: Metadata = { title: "Trims & options · prices" };

// Trims & options: plans are the trim levels, Secondary tools and services are the options (F1, F3).
export default function TrimsPage() {
  return (
    <SectionPage
      sectionId="trims"
      before={
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">Every price is set here, not in code</CardTitle>
            <CardDescription>
              Concierge onboarding is free at launch. Plans, Primary-tool caps, add-on prices, regional prices and
              coupons are added to this section with billing (P8).
            </CardDescription>
          </CardHeader>
          <CardContent />
        </Card>
      }
      fittings={[
        { label: "Plans & tiers", phase: "P8", detail: "trim levels with Primary-tool caps (M-10)" },
        { label: "Add-on prices", phase: "P8", detail: "Secondary tools per currency and region" },
        { label: "Coupons and trials", phase: "P8", detail: "promotions with expiry and usage limits" },
      ]}
    />
  );
}
