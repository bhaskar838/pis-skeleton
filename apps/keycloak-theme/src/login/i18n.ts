import { i18nBuilder } from "keycloakify/login";

import type { ThemeName } from "../kc.gen";

const { useI18n, ofTypeI18n } = i18nBuilder
  .withThemeName<ThemeName>()
  .withCustomTranslations({
    en: {
      loginAccountTitle: "Sign in to DCS-PIS",
      registerTitle: "Create your DCS-PIS account",
      loginTotpTitle: "Set up two-factor authentication",
      doLogIn: "Sign in",
    },
  })
  .build();

type I18n = typeof ofTypeI18n;

export { type I18n, useI18n };
