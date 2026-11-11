import { Badge, Card, CardContent, CardDescription, CardHeader, CardTitle, EmptyState } from "@dcs/ui";
import Link from "next/link";

import { resetSetting } from "@/app/(console)/panel-actions";
import { SubmitButton } from "@/components/form-bits";
import { SecretEditor, SettingEditor } from "@/components/setting-editor";
import { type ConfigSection, canWrite, displayValue, sourceLabel } from "@/lib/panel";

/** Every setting of one car section, each with its editor, source, default, history link and reset. */
export function SettingsSection({
  section,
  path,
  permissions,
  emptyHint,
}: {
  section: ConfigSection;
  path: string;
  permissions: ReadonlySet<string>;
  emptyHint?: string;
}) {
  if (section.settings.length === 0) {
    return <EmptyState title="Nothing to adjust here yet" description={emptyHint ?? "Settings for this part arrive with its phase."} />;
  }
  return (
    <div className="flex flex-col gap-4">
      {section.settings.map((s) => {
        const writable = canWrite(s, permissions);
        const src = sourceLabel(s);
        return (
          <Card key={s.key}>
            <CardHeader className="pb-2">
              <CardTitle className="flex flex-wrap items-center gap-2 text-base">
                {s.label}
                <Badge tone={src.tone}>{src.text}</Badge>
                {s.public ? <Badge>Shown to customers</Badge> : null}
                {s.used_from !== "P0.5" ? <Badge tone="warning">Used from {s.used_from}</Badge> : null}
              </CardTitle>
              <CardDescription>
                {s.help} <span className="font-mono text-[11px]">{s.key}</span>
              </CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-2">
              {s.type === "secret" ? (
                <SecretEditor setting={s} path={path} writable={writable} />
              ) : (
                <SettingEditor setting={s} path={path} writable={writable} />
              )}
              <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
                {s.type !== "secret" ? <span>Default: {displayValue(s.default)}</span> : null}
                {s.min !== null || s.max !== null ? (
                  <span>
                    Range: {s.min ?? "…"} – {s.max ?? "…"}
                  </span>
                ) : null}
                <Link href={`/config/${s.key}`} className="underline">
                  History
                </Link>
                {writable && s.source === "panel" && s.type !== "secret" ? (
                  <form action={resetSetting}>
                    <input type="hidden" name="key" value={s.key} />
                    <input type="hidden" name="path" value={path} />
                    <SubmitButton size="sm" variant="ghost">
                      Reset to default
                    </SubmitButton>
                  </form>
                ) : null}
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}
