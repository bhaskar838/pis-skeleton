import type { Metadata } from "next";

import { SectionPage } from "@/components/section-page";

export const metadata: Metadata = { title: "Engine bay · tools" };

// Engine bay: Floor 3. The engine (analysis tools) is built by another team and drops in through the ERI.
export default function EngineBayPage() {
  return (
    <SectionPage
      sectionId="engine_bay"
      fittings={[
        { label: "Tool registry", phase: "P3", detail: "import tools by digest, contract tests, rollout and retire (M-09)" },
        { label: "Assignment thresholds", phase: "P3", detail: "readiness scores that make a tool Primary, Secondary or Locked" },
        { label: "Sandbox limits", phase: "P3", detail: "CPU, memory and time per tool run" },
      ]}
    />
  );
}
