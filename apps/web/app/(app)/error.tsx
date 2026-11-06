"use client";

import { Button, ErrorState } from "@dcs/ui";
import { useEffect } from "react";

export default function AppError({ error, reset }: { error: Error & { digest?: string }; reset: () => void }) {
  useEffect(() => {
    console.error(error);
  }, [error]);
  return (
    <ErrorState
      title="Something went wrong"
      description={error.digest ? `Reference: ${error.digest}` : "We couldn't load this page. Try again in a moment."}
      action={
        <Button variant="outline" size="sm" onClick={reset}>
          Try again
        </Button>
      }
    />
  );
}
