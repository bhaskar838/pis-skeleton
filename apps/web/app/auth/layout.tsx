import type { ReactNode } from "react";

import { getBrand } from "@/lib/brand";

export default async function AuthLayout({ children }: { children: ReactNode }) {
  const brand = await getBrand();
  return (
    <main className="flex min-h-screen flex-col items-center justify-center bg-muted/40 p-6">
      <div className="mb-6 flex items-center gap-2 text-lg font-semibold">
        <svg viewBox="0 0 32 32" className="h-7 w-7" aria-hidden>
          <rect width="32" height="32" rx="7" fill="currentColor" className="text-primary" />
          <path d="M9 9h7a7 7 0 0 1 0 14H9z" fill="none" stroke="white" strokeWidth="3" />
        </svg>
        {brand.product_name}
      </div>
      <div className="w-full max-w-md">{children}</div>
      <footer className="mt-6 flex gap-4 text-xs text-muted-foreground">
        {brand.terms_url ? <a href={brand.terms_url} className="hover:underline">Terms</a> : null}
        {brand.privacy_url ? <a href={brand.privacy_url} className="hover:underline">Privacy</a> : null}
        {brand.support_email ? <a href={`mailto:${brand.support_email}`} className="hover:underline">{brand.support_email}</a> : null}
      </footer>
    </main>
  );
}
