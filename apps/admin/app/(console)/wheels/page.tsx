import type { Metadata } from "next";

import { SectionPage } from "@/components/section-page";

export const metadata: Metadata = { title: "Wheels · acquisition" };

// Wheels: Floor 1, how data gets in. Each acquisition phase adds its limits and switches here.
export default function WheelsPage() {
  return (
    <SectionPage
      sectionId="wheels"
      fittings={[
        { label: "Upload limits, virus scanning, archive limits", phase: "P1", detail: "file size, bomb limits, ClamAV" },
        { label: "E-mail-in and SFTP", phase: "P1", detail: "sender allowlists, inbound domains, SFTP keys" },
        { label: "Parsers on/off", phase: "P1", detail: "enable or quarantine each file format family" },
        { label: "Connector catalog", phase: "P4", detail: "enable, disable and version each connector (M-04)" },
        { label: "Bridge agents", phase: "P5", detail: "rollout rings and revocation (M-06)" },
        { label: "Browser recipes", phase: "P6", detail: "publish and health-check recipes (M-05)" },
      ]}
    />
  );
}
