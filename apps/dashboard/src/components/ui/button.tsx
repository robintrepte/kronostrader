"use client";

import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";

import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-1.5 rounded-md border font-mono text-[11px] tracking-wide uppercase transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--gold)]/50 disabled:pointer-events-none disabled:opacity-50 [&_svg]:pointer-events-none [&_svg]:shrink-0",
  {
    variants: {
      variant: {
        default:
          "border-[var(--border)] bg-[var(--panel)] text-[var(--foreground)] hover:border-[var(--gold)]",
        primary:
          "border-[color-mix(in_srgb,var(--gold)_55%,var(--border))] bg-[color-mix(in_srgb,var(--gold)_18%,var(--panel))] text-[var(--foreground)] hover:border-[var(--gold)]",
        ghost:
          "border-transparent bg-transparent text-[var(--muted)] hover:border-[var(--border)] hover:bg-[var(--panel)] hover:text-[var(--foreground)]",
      },
      size: {
        default: "min-h-9 min-w-9 px-3 py-1.5",
        sm: "min-h-8 min-w-8 px-2.5 py-1 text-[10px]",
        lg: "min-h-11 min-w-11 px-4 py-2",
        icon: "size-9 p-0",
        "icon-sm": "size-8 p-0",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  },
);

function Button({
  className,
  variant,
  size,
  asChild = false,
  ...props
}: React.ComponentProps<"button"> &
  VariantProps<typeof buttonVariants> & {
    asChild?: boolean;
  }) {
  const Comp = asChild ? Slot : "button";
  return (
    <Comp
      data-slot="button"
      className={cn(buttonVariants({ variant, size, className }))}
      {...props}
    />
  );
}

export { Button, buttonVariants };
