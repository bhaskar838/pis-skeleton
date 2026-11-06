import type { ReactNode } from "react";

export default function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-muted/40 p-6">
      <div className="mb-6 flex items-center gap-2 text-lg font-semibold">
        <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
          <rect width="32" height="32" rx="7" fill="currentColor" className="text-primary" />
          <path d="M9 9h7a7 7 0 0 1 0 14H9z" fill="none" stroke="white" strokeWidth="3" />
        </svg>
        DCS-PIS
      </div>
      <div className="w-full max-w-md">{children}</div>
    </main>
  );
}
