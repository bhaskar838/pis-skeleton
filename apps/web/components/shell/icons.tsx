import { Database, House, IndianRupee, Lightbulb, Settings, Share2, Sparkles } from "lucide-react";

import type { IconName } from "@/lib/nav";

const ICONS = {
  home: House,
  sources: Share2,
  studio: Database,
  toolkit: Sparkles,
  insights: Lightbulb,
  billing: IndianRupee,
  settings: Settings,
} as const;

export function NavIcon({ name }: { name?: IconName }) {
  if (!name) return null;
  const Icon = ICONS[name];
  return <Icon className="h-4 w-4 shrink-0" aria-hidden />;
}
