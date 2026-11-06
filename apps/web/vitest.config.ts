import path from "node:path";

import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  resolve: { alias: { "@": path.resolve(__dirname, "."), "server-only": path.resolve(__dirname, "test/server-only.ts") } },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./test/setup.ts"],
    include: ["**/*.test.ts", "**/*.test.tsx"],
    exclude: ["node_modules", ".next"],
    coverage: {
      include: ["lib/**/*.ts", "components/**/*.tsx"],
      exclude: ["lib/session.ts", "lib/api.ts", "lib/context.ts", "lib/problem.ts", "lib/auth-policy.ts"],
      thresholds: { lines: 70 },
    },
  },
});
