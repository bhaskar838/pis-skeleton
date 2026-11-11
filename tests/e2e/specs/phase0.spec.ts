/**
 * Phase 0 E2E (SPEC §13 P0 tests):
 *  1. sign-up → MFA enrol → land on home
 *  2. invite a user → accept → limited role sees limited nav
 */
import { expect, test } from "@playwright/test";

import { enrolTotp, expectNav, firstLink, latestMail, registerOnKeycloak, uniqueEmail, verifyEmail } from "./helpers";

const OWNER_STATE = "test-results/.auth/owner.json";

test.describe.configure({ mode: "serial" });

const ownerEmail = uniqueEmail("owner");
const analystEmail = uniqueEmail("analyst");

test("sign-up → MFA enrol → home", async ({ page }) => {
  await page.goto("/auth/sign-up");
  await page.getByLabel("Company name").fill("Northwind Fitness");
  await page.getByLabel("Country").selectOption("IN");
  await page.getByRole("button", { name: "Continue" }).click();

  await page.waitForURL(/keycloak\.localhost/);
  await registerOnKeycloak(page, ownerEmail);
  await verifyEmail(page, ownerEmail);

  // Owner role needs MFA: the app sends the user to A-04, which steps up to Keycloak OTP enrolment.
  await page.waitForURL(/\/auth\/mfa|keycloak\.localhost|localhost:3000\/$/);
  if (page.url().includes("/auth/mfa")) {
    await page.getByRole("button", { name: /two-factor/i }).click();
  }
  await page.waitForURL(/keycloak\.localhost/);
  await enrolTotp(page);

  await page.waitForURL("http://localhost:3000/");
  await expect(page.getByRole("heading", { name: /Home · Northwind Fitness/ })).toBeVisible();
  // Provisioning finishes in < 30 s; the page updates live (WebSocket) or via fallback refresh.
  await expect(page.getByText("active", { exact: true })).toBeVisible({ timeout: 45_000 });
  await expectNav(page, ["Home", "Data Sources", "Data Studio", "Toolkit", "Insights", "Billing", "Settings"], []);
  await page.context().storageState({ path: OWNER_STATE }); // reused by the invite journey
});

test("invite → accept → limited nav", async ({ browser }) => {
  // The owner's MFA-verified session from the sign-up journey.
  const ownerCtx = await browser.newContext({ storageState: OWNER_STATE });
  const owner = await ownerCtx.newPage();
  await owner.goto("/settings/team");
  await owner.getByLabel("E-mail address").fill(analystEmail);
  await owner.getByLabel("Role").selectOption("analyst");
  await owner.getByRole("button", { name: "Send invitation" }).click();
  await expect(owner.getByText(`Invitation sent to ${analystEmail}`)).toBeVisible();

  const mail = await latestMail(analystEmail, "invited");
  const ctx = await browser.newContext();
  const analyst = await ctx.newPage();
  await analyst.goto(firstLink(mail.text, "/auth/invite/"));
  await expect(analyst.getByRole("heading", { name: /Join Northwind Fitness/ })).toBeVisible();
  await analyst.getByRole("button", { name: "Sign in to accept" }).click();
  await analyst.waitForURL(/keycloak\.localhost/);
  await analyst.getByRole("link", { name: /register/i }).click();
  await registerOnKeycloak(analyst, analystEmail);
  await verifyEmail(analyst, analystEmail);
  await analyst.waitForURL(/\/auth\/invite\//);
  await analyst.getByRole("button", { name: "Accept invitation" }).click();

  await analyst.waitForURL("http://localhost:3000/");
  await expectNav(analyst, ["Home", "Data Studio", "Toolkit", "Insights", "Settings"], ["Data Sources", "Billing"]);
  await analyst.goto("/settings/team");
  await expect(analyst.getByText("You don't have access to this page")).toBeVisible();
});

test("security headers are present", async ({ request }) => {
  const res = await request.get("/auth/sign-in");
  expect(res.headers()["content-security-policy"]).toContain("frame-ancestors 'none'");
  expect(res.headers()["strict-transport-security"]).toContain("max-age=");
});

test("staff console: first login (password change + TOTP) → M-02 lists the tenant", async ({ browser }) => {
  const initial = process.env.E2E_STAFF_PASSWORD;
  test.skip(!initial, "set E2E_STAFF_PASSWORD (DCS_KC_STAFF_PASSWORD from .env)");
  const ctx = await browser.newContext({ baseURL: process.env.E2E_ADMIN_URL ?? "http://localhost:3001" });
  const staff = await ctx.newPage();
  await staff.goto("/auth/sign-in");
  await staff.getByRole("button", { name: /staff SSO/i }).click();
  await staff.waitForURL(/keycloak\.localhost/);
  await staff.locator("#username").fill("staff@dcs.local");
  await staff.locator("#password").fill(initial ?? "");
  await staff.locator("#kc-login").click();
  // First login: Keycloak asks for a new password and TOTP enrolment (order depends on required-action priority).
  for (let step = 0; step < 3 && staff.url().includes("keycloak"); step++) {
    if (await staff.locator("#password-new").isVisible().catch(() => false)) {
      await staff.locator("#password-new").fill("Staff-Console-Pass-2026!");
      await staff.locator("#password-confirm").fill("Staff-Console-Pass-2026!");
      await staff.locator("input[type=submit], button[type=submit]").first().click();
    } else if (await staff.getByText(/unable to scan/i).isVisible().catch(() => false)) {
      await enrolTotp(staff);
    }
    await staff.waitForLoadState("domcontentloaded");
  }
  await staff.waitForURL(/localhost:3001\/$/);
  await expect(staff.getByRole("heading", { name: "Instrument cluster" })).toBeVisible();
  await staff.getByRole("link", { name: "Tenants" }).click();
  await expect(staff.getByRole("link", { name: "Northwind Fitness" }).first()).toBeVisible();

  // Phase 0.5 (ADR-0011): a Body change in the control panel reaches the customer app without a deploy.
  await staff.getByRole("link", { name: "Brand & legal" }).click();
  await staff.getByLabel("Product name value").fill("Northwind Panel Check");
  await staff.getByRole("button", { name: "Save" }).first().click();
  await expect(staff.getByText(/Saved\. Live everywhere/)).toBeVisible();
  const visitor = await browser.newPage();
  await expect(async () => {
    await visitor.goto(`${process.env.E2E_WEB_URL ?? "http://localhost:3000"}/auth/sign-in`);
    await expect(visitor.getByText("Use your Northwind Panel Check account", { exact: false })).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 20_000 });
  await staff.getByRole("button", { name: "Reset to default" }).click();
  await expect(staff.getByLabel("Product name value")).toHaveValue("DCS-PIS");

  // Chassis: the four-region world map with India and Europe live (ADR-0012).
  await staff.getByRole("link", { name: "Regions & limits" }).click();
  const regions = staff.getByRole("table").first();
  await expect(regions.getByRole("row", { name: /Mumbai.*active/ })).toBeVisible();
  await expect(regions.getByRole("row", { name: /N\. Virginia.*planned/ })).toBeVisible();
  await visitor.close();
});

test("sign-up offers only the countries open in the control panel", async ({ page }) => {
  await page.goto("/auth/sign-up");
  const country = page.getByLabel("Country");
  await expect(country.locator("option[value=IN]")).toHaveCount(1);
  await expect(country.locator("option[value=DE]")).toHaveCount(1);
  await expect(country.locator("option[value=US]")).toHaveCount(0);
  await expect(country.locator("option[value=SG]")).toHaveCount(0);
});
