import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    coverage: { include: ["src/**/*.tsx", "src/**/*.ts"], exclude: ["src/index.ts"], thresholds: { lines: 70 } },
  },
});
