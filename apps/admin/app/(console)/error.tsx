"use client";

import { Button, ErrorState } from "@dcs/ui";

export default function ConsoleError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <ErrorState
      description={error.digest ? `Reference: ${error.digest}` : "This page failed to load."}
      action={
        <Button variant="outline" size="sm" onClick={reset}>
          Try again
        </Button>
      }
    />
  );
}
