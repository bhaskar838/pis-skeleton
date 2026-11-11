"use client";

import { Badge, cn } from "@dcs/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { type AdminNavGroup, isActive } from "@/lib/nav";

export function AdminSidebar({ groups }: { groups: AdminNavGroup[] }) {
  const pathname = usePathname() ?? "/";
  return (
    <nav aria-label="Admin" className="flex flex-col gap-3 p-3 text-sm">
      {groups.map((g) => (
        <section key={g.part} aria-labelledby={`nav-${slug(g.part)}`}>
          <h2 id={`nav-${slug(g.part)}`} className="px-3 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">
            {g.part}
          </h2>
          <p className="px-3 pb-1 text-[11px] text-muted-foreground/80">{g.hint}</p>
          <ul className="flex flex-col gap-0.5">
            {g.items.map((i) => (
              <li key={i.href}>
                {i.soon ? (
                  <span aria-disabled="true" className="flex items-center justify-between rounded-md px-3 py-1.5 text-muted-foreground opacity-70">
                    {i.label} <Badge>{i.soon}</Badge>
                  </span>
                ) : (
                  <Link
                    href={i.href}
                    aria-current={isActive(i.href, pathname) ? "page" : undefined}
                    className={cn("block rounded-md px-3 py-1.5 hover:bg-muted", isActive(i.href, pathname) && "bg-accent font-medium text-primary")}
                  >
                    {i.label}
                  </Link>
                )}
              </li>
            ))}
          </ul>
        </section>
      ))}
    </nav>
  );
}

function slug(s: string): string {
  return s.toLowerCase().replace(/[^a-z0-9]+/g, "-");
}
