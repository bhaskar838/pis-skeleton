import { Button, EmptyState } from "@dcs/ui";
import Link from "next/link";

export default function NotFound() {
  return (
    <main className="mx-auto max-w-lg p-12">
      <EmptyState
        title="Not found"
        description="This page or tenant does not exist."
        action={
          <Button asChild variant="outline" size="sm">
            <Link href="/">Back to dashboard</Link>
          </Button>
        }
      />
    </main>
  );
}
