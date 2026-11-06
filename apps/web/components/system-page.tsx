import { Button, Card } from "@dcs/ui";
import Link from "next/link";
import type { ReactNode } from "react";

/** X-03 system pages share one centred layout. */
export function SystemPage({
  code,
  title,
  body,
  action,
}: {
  code?: string;
  title: string;
  body: string;
  action?: ReactNode;
}) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-muted/40 p-6">
      <Card className="w-full max-w-md p-8 text-center">
        {code ? <p className="text-sm font-semibold tracking-widest text-primary">{code}</p> : null}
        <h1 className="mt-2 text-2xl font-semibold tracking-tight">{title}</h1>
        <p className="mt-2 text-sm text-muted-foreground">{body}</p>
        <div className="mt-6 flex justify-center gap-2">
          {action ?? (
            <Button asChild>
              <Link href="/">Go to home</Link>
            </Button>
          )}
        </div>
      </Card>
    </main>
  );
}
