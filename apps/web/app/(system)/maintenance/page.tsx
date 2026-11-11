import type { Metadata } from "next";

import { SystemPage } from "@/components/system-page";
import { getBrand } from "@/lib/brand";

export const metadata: Metadata = { title: "Maintenance" };

export default async function Maintenance() {
  const { product_name: name } = await getBrand();
  return (
    <SystemPage
      title="We'll be right back"
      body={`${name} is undergoing scheduled maintenance. Your data is safe; syncs resume automatically afterwards.`}
    />
  );
}
