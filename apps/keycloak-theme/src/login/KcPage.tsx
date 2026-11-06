/**
 * DCS-PIS login theme (A-01 sign-in, A-02 registration, A-03 reset, A-04 OTP/WebAuthn enrol + verify).
 * Uses Keycloakify's default page implementations with DCS branding; field ids stay standard so the E2E suite
 * works with both the default and the DCS theme.
 */
import "./main.css";

import type { ClassKey } from "keycloakify/login";
import DefaultPage from "keycloakify/login/DefaultPage";
import Template from "keycloakify/login/Template";
import { lazy, Suspense } from "react";

import { useI18n } from "./i18n";
import type { KcContext } from "./KcContext";

const UserProfileFormFields = lazy(() => import("keycloakify/login/UserProfileFormFields"));

const classes = {
  kcHtmlClass: "dcs-html",
  kcBodyClass: "dcs-body",
  kcHeaderWrapperClass: "dcs-header",
  kcFormCardClass: "dcs-card",
  kcButtonPrimaryClass: "dcs-btn-primary",
  kcInputClass: "dcs-input",
} satisfies { [key in ClassKey]?: string };

export default function KcPage({ kcContext }: { kcContext: KcContext }) {
  const { i18n } = useI18n({ kcContext });
  return (
    <Suspense>
      <DefaultPage
        kcContext={kcContext}
        i18n={i18n}
        classes={classes}
        Template={Template}
        doUseDefaultCss={true}
        UserProfileFormFields={UserProfileFormFields}
        doMakeUserConfirmPassword={true}
      />
    </Suspense>
  );
}
