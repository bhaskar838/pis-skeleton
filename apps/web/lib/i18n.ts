import messages from "@/messages/en.json";

export type MessageKey = keyof typeof messages;

/** English-first i18n (SPEC §9.4). Unknown keys return the key, which tests catch. */
export function t(key: MessageKey | string): string {
  return (messages as Record<string, string>)[key] ?? key;
}
