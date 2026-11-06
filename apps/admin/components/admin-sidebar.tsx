"use client";

import { Badge, cn } from "@dcs/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { type AdminNavItem, isActive } from "@/lib/nav";

export function AdminSidebar({ items }: { items: AdminNavItem[] }) {
  const pathname = usePathname() ?? "/";
  return (
    <nav aria-label="Admin" className="flex flex-col gap-0.5 p-3 text-sm">
      {items.map((i) =>
        i.soon ? (
          <span key={i.href} aria-disabled="true" className="flex items-center justify-between rounded-md px-3 py-2 text-muted-foreground opacity-70">
            {i.label} <Badge>Soon</Badge>
          </span>
        ) : (
          <Link
            key={i.href}
            href={i.href}
            aria-current={isActive(i.href, pathname) ? "page" : undefined}
            className={cn("rounded-md px-3 py-2 hover:bg-muted", isActive(i.href, pathname) && "bg-accent font-medium text-primary")}
          >
            {i.label}
          </Link>
        ),
      )}
    </nav>
  );
}
