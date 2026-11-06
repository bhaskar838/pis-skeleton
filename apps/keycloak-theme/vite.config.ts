import react from "@vitejs/plugin-react";
import { keycloakify } from "keycloakify/vite-plugin";
import { defineConfig } from "vite";

// `keycloakify build` writes dist_keycloak/keycloak-theme-*.jar, mounted into Keycloak's providers dir by
// docker-compose. Then set DCS_KC_LOGIN_THEME=dcs. Building the JAR needs Maven + Java (CI / image build).
export default defineConfig({
  plugins: [
    react(),
    keycloakify({
      themeName: "dcs",
      accountThemeImplementation: "none",
      keycloakVersionTargets: { "22-to-25": false, "all-other-versions": "keycloak-theme.jar" },
    }),
  ],
});
