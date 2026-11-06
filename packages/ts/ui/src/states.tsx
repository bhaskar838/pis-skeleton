/**
 * The four mandatory page states (SPEC §0.3 DoD, §9.4): loading, empty (with the next action), error, forbidden.
 */
import { AlertTriangle, Inbox, Lock } from "lucide-react";
import type * as React from "react";

import { cn } from "./cn";
import { Card, Skeleton } from "./primitives";

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: React.ReactNode }) {
  return (
    <div className="mb-6 flex flex-wrap items-start justify-between gap-4">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
        {description ? <p className="mt-1 text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {actions ? <div className="flex items-center gap-2">{actions}</div> : null}
    </div>
  );
}

interface StateProps {
  title: string;
  description?: string;
  action?: React.ReactNode;
  className?: string;
}

function StateBox({ icon, title, description, action, className, role }: StateProps & { icon: React.ReactNode; role?: string }) {
  return (
    <Card role={role} className={cn("flex flex-col items-center justify-center gap-3 px-6 py-12 text-center", className)}>
      <div className="rounded-full bg-muted p-3 text-muted-foreground">{icon}</div>
      <div>
        <p className="font-medium">{title}</p>
        {description ? <p className="mt-1 max-w-md text-sm text-muted-foreground">{description}</p> : null}
      </div>
      {action}
    </Card>
  );
}

export function EmptyState(props: StateProps) {
  return <StateBox icon={<Inbox className="h-5 w-5" aria-hidden />} {...props} />;
}

export function ErrorState({ title = "Something went wrong", ...props }: Partial<StateProps>) {
  return <StateBox role="alert" icon={<AlertTriangle className="h-5 w-5 text-destructive" aria-hidden />} title={title} {...props} />;
}

export function ForbiddenState({
  title = "You don't have access to this page",
  description = "Your role doesn't include this permission. Ask an owner or admin of your organisation.",
  ...props
}: Partial<StateProps>) {
  return <StateBox icon={<Lock className="h-5 w-5" aria-hidden />} title={title} description={description} {...props} />;
}

export function LoadingState({ rows = 4, label = "Loading" }: { rows?: number; label?: string }) {
  return (
    <div role="status" aria-label={label} className="flex flex-col gap-3">
      <Skeleton className="h-8 w-1/3" />
      {Array.from({ length: rows }, (_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warning" | "danger" | "success"; children: React.ReactNode }) {
  const tones = {
    info: "border-border bg-accent",
    warning: "border-warning/40 bg-muted text-warning",
    danger: "border-destructive/40 bg-muted text-destructive",
    success: "border-success/40 bg-muted text-success",
  } as const;
  return (
    <div role={tone === "danger" ? "alert" : "status"} className={cn("rounded-md border px-4 py-3 text-sm", tones[tone])}>
      {children}
    </div>
  );
}
