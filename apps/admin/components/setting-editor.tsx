"use client";

import { Input, Select } from "@dcs/ui";
import { useActionState } from "react";

import { clearSecret, saveSecret, saveSetting } from "@/app/(console)/panel-actions";
import { FormMessage, SubmitButton } from "@/components/form-bits";
import { CURRENCIES, type Setting } from "@/lib/panel";

/** Editor for one non-secret setting. The API validates again; this only shapes the input. */
export function SettingEditor({ setting, path, writable }: { setting: Setting; path: string; writable: boolean }) {
  const [state, action] = useActionState(saveSetting, null);
  const id = `setting-${setting.key}`;
  return (
    <form action={action} className="flex flex-col gap-2">
      <input type="hidden" name="key" value={setting.key} />
      <input type="hidden" name="type" value={setting.type} />
      <input type="hidden" name="path" value={path} />
      <div className="flex flex-wrap items-end gap-2">
        {/* Keyed by version + source: after a save, reset or revert the input shows the stored value. */}
        <ValueInput key={`${setting.version}:${setting.source}`} id={id} setting={setting} disabled={!writable} />
        {writable ? <SubmitButton size="sm">Save</SubmitButton> : null}
      </div>
      <FormMessage state={state} />
    </form>
  );
}

function ValueInput({ id, setting, disabled }: { id: string; setting: Setting; disabled: boolean }) {
  const label = `${setting.label} value`;
  switch (setting.type) {
    case "bool":
      return (
        <label className="flex items-center gap-2 text-sm">
          <input id={id} type="checkbox" name="value" defaultChecked={setting.value === true} disabled={disabled} aria-label={label} />
          Enabled
        </label>
      );
    case "enum":
      return (
        <Select id={id} name="value" defaultValue={String(setting.value ?? "")} disabled={disabled} aria-label={label} className="w-48">
          {setting.choices.map((c) => (
            <option key={c} value={c}>
              {c}
            </option>
          ))}
        </Select>
      );
    case "int":
      return (
        <Input
          id={id}
          name="value"
          type="number"
          inputMode="numeric"
          min={setting.min ?? undefined}
          max={setting.max ?? undefined}
          defaultValue={String(setting.value ?? "")}
          disabled={disabled}
          aria-label={label}
          className="w-32"
        />
      );
    case "money": {
      const prices = (setting.value ?? {}) as Record<string, string>;
      return (
        <div className="flex flex-wrap gap-2">
          {CURRENCIES.map((c) => (
            <label key={c} className="flex items-center gap-1 text-xs text-muted-foreground">
              {c}
              <Input name={`amount_${c}`} inputMode="decimal" placeholder="0.00" defaultValue={prices[c] ?? ""} disabled={disabled} aria-label={`${setting.label} ${c}`} className="w-28" />
            </label>
          ))}
        </div>
      );
    }
    default:
      return (
        <Input
          id={id}
          name="value"
          type={setting.type === "email" ? "email" : setting.type === "url" ? "url" : "text"}
          defaultValue={String(setting.value ?? "")}
          disabled={disabled}
          aria-label={label}
          className="min-w-64 flex-1"
        />
      );
  }
}

/** Write-only editor: the current value is never sent to the browser, only whether one is set. */
export function SecretEditor({ setting, path, writable }: { setting: Setting; path: string; writable: boolean }) {
  const [state, action] = useActionState(saveSecret, null);
  return (
    <div className="flex flex-col gap-2">
      <p className="text-sm">
        {setting.is_set ? (
          <>
            <span className="font-medium text-success">Set</span>
            {setting.version ? ` · v${setting.version}` : " · from deployment"}
            {setting.updated_by ? ` · by ${setting.updated_by}` : ""}
            {setting.updated_at ? ` · ${new Date(setting.updated_at).toUTCString()}` : ""}
          </>
        ) : (
          <span className="text-muted-foreground">Not set</span>
        )}
      </p>
      {writable ? (
        <div className="flex flex-wrap items-end gap-2">
          <form action={action} className="flex flex-wrap items-end gap-2">
            <input type="hidden" name="key" value={setting.key} />
            <input type="hidden" name="path" value={path} />
            <Input key={setting.version} name="value" type="password" autoComplete="new-password" placeholder={setting.is_set ? "Enter a new value to rotate" : "Enter value"} aria-label={`${setting.label} new value`} className="min-w-64" />
            <SubmitButton size="sm">{setting.is_set ? "Rotate" : "Save"}</SubmitButton>
          </form>
          {setting.version ? (
            <form action={clearSecret}>
              <input type="hidden" name="key" value={setting.key} />
              <input type="hidden" name="path" value={path} />
              <SubmitButton size="sm" variant="ghost">
                Clear
              </SubmitButton>
            </form>
          ) : null}
        </div>
      ) : (
        <p className="text-xs text-muted-foreground">Only staff admins can set secrets.</p>
      )}
      <FormMessage state={state} />
    </div>
  );
}
