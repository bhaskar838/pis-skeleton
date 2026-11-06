// OpenTelemetry for the Next.js server (SPEC P0-T14): traces propagate web → control-api → Temporal → worker.
import { registerOTel } from "@vercel/otel";

export function register() {
  registerOTel({ serviceName: "admin" });
}
