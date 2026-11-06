"use client";

import "./globals.css";

// X-03 500: last-resort boundary for errors in the root layout.
export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="en">
      <body className="flex min-h-screen items-center justify-center p-6">
        <div className="max-w-md text-center">
          <p className="text-sm font-semibold tracking-widest text-primary">500</p>
          <h1 className="mt-2 text-2xl font-semibold">Something went wrong</h1>
          <p className="mt-2 text-sm text-muted-foreground">An unexpected error occurred. Our team has been notified.</p>
          <button type="button" onClick={reset} className="mt-6 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground">
            Try again
          </button>
        </div>
      </body>
    </html>
  );
}
