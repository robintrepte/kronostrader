"use client";

import * as React from "react";
import * as SwitchPrimitive from "@radix-ui/react-switch";

import { cn } from "@/lib/utils";

function Switch({
  className,
  ...props
}: React.ComponentProps<typeof SwitchPrimitive.Root>) {
  return (
    <SwitchPrimitive.Root
      data-slot="switch"
      className={cn(
        "peer inline-flex h-6 w-11 shrink-0 cursor-pointer items-center rounded-full border border-[var(--border)] bg-[var(--border)] transition-colors",
        "data-[state=checked]:bg-[var(--mint)]/40 data-[state=unchecked]:bg-[var(--border)]",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gold)]/50",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    >
      <SwitchPrimitive.Thumb
        data-slot="switch-thumb"
        className={cn(
          "pointer-events-none block size-5 rounded-full bg-[var(--foreground)] shadow transition-transform",
          "data-[state=checked]:translate-x-[22px] data-[state=unchecked]:translate-x-0.5",
          "data-[state=checked]:bg-[var(--mint)]",
        )}
      />
    </SwitchPrimitive.Root>
  );
}

export { Switch };
