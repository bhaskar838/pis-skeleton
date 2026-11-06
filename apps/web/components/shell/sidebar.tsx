"use client";

import { Badge, cn } from "@dcs/ui";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { t } from "@/lib/i18n";
import { isActive, type NavItem } from "@/lib/nav";

import { NavIcon } from "./icons";

export function Sidebar({ items }: { items: NavItem[] }) {
  const pathname = usePathname() ?? "/";
  return (
    <nav aria-label="Main" className="flex flex-col gap-1 p-3 text-sm">
      {items.map((item) => (
        <div key={item.id}>
          {item.soon ? (
            <span
              aria-disabled="true"
              className="flex items-center gap-3 rounded-md px-3 py-2 text-muted-foreground opacity-70"
              title="Available in a coming release"
            >
              <NavIcon name={item.icon} />
              <span className="flex-1">{t(item.label)}</span>
              <Badge>{t("nav.soon")}</Badge>
            </span>
          ) : (
            <Link
              href={item.href}
              aria-current={isActive(item.href, pathname) && !item.children ? "page" : undefined}
              className={cn(
                "flex items-center gap-3 rounded-md px-3 py-2 hover:bg-muted",
                isActive(item.children ? "/settings" : item.href, pathname) && "bg-accent font-medium text-primary",
              )}
            >
              <NavIcon name={item.icon} />
              <span>{t(item.label)}</span>
            </Link>
          )}
          {item.children && pathname.startsWith("/settings") ? (
            <div className="ml-7 mt-1 flex flex-col gap-0.5 border-l border-border pl-3">
              {item.children.map((child) => (
                <Link
                  key={child.id}
                  href={child.href}
                  aria-current={isActive(child.href, pathname) ? "page" : undefined}
                  className={cn(
                    "rounded px-2 py-1.5 text-muted-foreground hover:bg-muted hover:text-foreground",
                    isActive(child.href, pathname) && "bg-muted font-medium text-foreground",
                  )}
                >
                  {t(child.label)}
                </Link>
              ))}
            </div>
          ) : null}
        </div>
      ))}
    </nav>
  );
}
