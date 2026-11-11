import "./globals.css";

import type { Metadata, Viewport } from "next";
import type { ReactNode } from "react";

import { getBrand } from "@/lib/brand";

// The product name is set in the admin control panel (Body → Product name, F6).
export async function generateMetadata(): Promise<Metadata> {
  const { product_name: name } = await getBrand();
  return {
    title: { default: name, template: `%s · ${name}` },
    description: "Predictive Intelligence System by Datachondria Systems",
    icons: { icon: "/favicon.svg" },
  };
}

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen">{children}</body>
    </html>
  );
}
