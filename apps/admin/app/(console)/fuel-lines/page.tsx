import type { Metadata } from "next";

import { SectionPage } from "@/components/section-page";

export const metadata: Metadata = { title: "Fuel lines · shaping" };

// Fuel lines: Floor 2, how raw data becomes the canonical model.
export default function FuelLinesPage() {
  return (
    <SectionPage
      sectionId="fuel_lines"
      fittings={[
        { label: "Model Gateway", phase: "P2", detail: "providers, routing rules, prompt versions, spend caps (M-11)" },
        { label: "Mapping review thresholds", phase: "P2", detail: "auto-approve confidence, reviewer rules" },
        { label: "CBM versions and templates", phase: "P2", detail: "field dictionary and connector templates (M-07)" },
        { label: "Data quality and drift rules", phase: "P7", detail: "thresholds that raise tasks for customers" },
      ]}
    />
  );
}
