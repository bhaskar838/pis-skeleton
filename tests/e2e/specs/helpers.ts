import { expect, type Page } from "@playwright/test";
import { TOTP } from "otpauth";

const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://localhost:8025";

export function uniqueEmail(prefix: string): string {
  return `${prefix}.${Date.now()}.${Math.floor(Math.random() * 1e6)}@example.test`;
}

export const PASSWORD = "Correct-Horse-Battery-9";

/** Latest e-mail to `to` from Mailpit (dev SMTP sink). */
export async function latestMail(to: string, subjectIncludes: string): Promise<{ text: string }> {
  for (let i = 0; i < 30; i++) {
    const res = await fetch(`${MAILPIT}/api/v1/search?query=${encodeURIComponent(`to:"${to}"`)}`);
    const list = (await res.json()) as { messages: { ID: string; Subject: string }[] };
    const hit = list.messages.find((m) => m.Subject.includes(subjectIncludes));
    if (hit) {
      const msg = (await (await fetch(`${MAILPIT}/api/v1/message/${hit.ID}`)).json()) as { Text: string };
      return { text: msg.Text };
    }
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error(`no mail to ${to} with subject containing "${subjectIncludes}"`);
}

export function firstLink(text: string, contains: string): string {
  const match = text.match(new RegExp(`https?://\\S*${contains}\\S*`));
  if (!match) throw new Error(`no link containing ${contains}`);
  return match[0].replace(/&amp;/g, "&");
}

/** Keycloak registration form (default or Keycloakify theme — both keep the standard field ids). */
export async function registerOnKeycloak(page: Page, email: string): Promise<void> {
  await page.locator("#email").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.locator("#password-confirm").fill(PASSWORD);
  const first = page.locator("#firstName");
  if (await first.isVisible()) await first.fill("Asha");
  const last = page.locator("#lastName");
  if (await last.isVisible()) await last.fill("Rao");
  await page.locator("input[type=submit], button[type=submit]").first().click();
}

/** Complete Keycloak's "verify email" step by opening the link from Mailpit. */
export async function verifyEmail(page: Page, email: string): Promise<void> {
  const mail = await latestMail(email, "erif");
  await page.goto(firstLink(mail.text, "action-token"));
  const proceed = page.getByRole("link", { name: /click here to proceed|back to application/i });
  if (await proceed.isVisible().catch(() => false)) await proceed.click();
}

/** Enrol TOTP on Keycloak's CONFIGURE_TOTP page and return the secret for later codes. */
export async function enrolTotp(page: Page): Promise<string> {
  const scan = page.getByText(/unable to scan/i);
  const password = page.locator("#password");
  await expect(scan.or(password)).toBeVisible();
  if (await password.isVisible()) {
    // Some Keycloak configurations re-confirm the password before adding a factor.
    await password.fill(PASSWORD);
    await page.locator("input[type=submit], button[type=submit]").first().click();
  }
  await scan.click();
  const secretText = (await page.locator("#kc-totp-secret-key").innerText()).replace(/\s+/g, "");
  const totp = new TOTP({ secret: secretText, digits: 6, period: 30 });
  await page.locator("#totp").fill(totp.generate());
  await page.locator("input[type=submit], button[type=submit]").first().click();
  return secretText;
}

export async function signInOnKeycloak(page: Page, email: string): Promise<void> {
  await page.locator("#username").fill(email);
  await page.locator("#password").fill(PASSWORD);
  await page.locator("input[type=submit], button[type=submit]").first().click();
}

export async function expectNav(page: Page, visible: string[], hidden: string[]): Promise<void> {
  const nav = page.getByRole("navigation", { name: "Main" });
  for (const label of visible) await expect(nav.getByText(label, { exact: true })).toBeVisible();
  for (const label of hidden) await expect(nav.getByText(label, { exact: true })).toHaveCount(0);
}
