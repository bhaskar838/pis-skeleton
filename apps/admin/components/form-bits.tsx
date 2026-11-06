"use client";

import { Button, type ButtonProps } from "@dcs/ui";
import { useFormStatus } from "react-dom";

export function SubmitButton({ children, ...props }: ButtonProps) {
  const { pending } = useFormStatus();
  return (
    <Button type="submit" disabled={pending || props.disabled} aria-busy={pending} {...props}>
      {pending ? "Working…" : children}
    </Button>
  );
}

export function FormMessage({ state }: { state: { error?: string; message?: string; ok?: boolean } | null }) {
  if (!state) return null;
  if (state.error) return <p role="alert" className="text-sm text-destructive">{state.error}</p>;
  if (state.ok && state.message) return <p role="status" className="text-sm text-success">{state.message}</p>;
  return null;
}
