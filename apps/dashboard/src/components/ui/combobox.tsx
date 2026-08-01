"use client";

import * as React from "react";
import { Combobox as ComboboxPrimitive } from "@base-ui/react";
import { CheckIcon, ChevronDownIcon, XIcon } from "lucide-react";

import { cn } from "@/lib/utils";

const Combobox = ComboboxPrimitive.Root;

function ComboboxValue({ ...props }: ComboboxPrimitive.Value.Props) {
  return <ComboboxPrimitive.Value data-slot="combobox-value" {...props} />;
}

function ComboboxTrigger({
  className,
  children,
  showIcon = true,
  ...props
}: ComboboxPrimitive.Trigger.Props & { showIcon?: boolean }) {
  return (
    <ComboboxPrimitive.Trigger
      data-slot="combobox-trigger"
      className={cn("[&_svg:not([class*='size-'])]:size-4", className)}
      {...props}
    >
      {children}
      {showIcon ? (
        <ChevronDownIcon
          data-slot="combobox-trigger-icon"
          className="pointer-events-none size-4 shrink-0 text-[var(--muted)]"
        />
      ) : null}
    </ComboboxPrimitive.Trigger>
  );
}

function ComboboxInput({
  className,
  disabled = false,
  showTrigger = false,
  showClear = false,
  ...props
}: ComboboxPrimitive.Input.Props & {
  showTrigger?: boolean;
  showClear?: boolean;
}) {
  return (
    <div
      data-slot="input-group"
      className={cn(
        "flex h-9 w-full items-center gap-1 rounded-md border border-[var(--border)] bg-[var(--input)] px-2",
        className,
      )}
    >
      <ComboboxPrimitive.Input
        disabled={disabled}
        className="min-w-0 flex-1 bg-transparent py-1 text-sm text-[var(--foreground)] outline-none placeholder:text-[var(--muted)] disabled:cursor-not-allowed disabled:opacity-50"
        {...props}
      />
      {showTrigger ? (
        <ComboboxTrigger
          showIcon
          disabled={disabled}
          className="inline-flex size-6 items-center justify-center rounded text-[var(--muted)] hover:text-[var(--foreground)] disabled:opacity-50"
        />
      ) : null}
      {showClear ? (
        <ComboboxPrimitive.Clear
          data-slot="combobox-clear"
          disabled={disabled}
          className="inline-flex size-6 items-center justify-center rounded text-[var(--muted)] hover:text-[var(--foreground)] disabled:opacity-50"
        >
          <XIcon className="pointer-events-none size-3.5" />
        </ComboboxPrimitive.Clear>
      ) : null}
    </div>
  );
}

function ComboboxContent({
  className,
  side = "bottom",
  sideOffset = 6,
  align = "start",
  alignOffset = 0,
  anchor,
  ...props
}: ComboboxPrimitive.Popup.Props &
  Pick<
    ComboboxPrimitive.Positioner.Props,
    "side" | "align" | "sideOffset" | "alignOffset" | "anchor"
  >) {
  return (
    <ComboboxPrimitive.Portal>
      <ComboboxPrimitive.Positioner
        side={side}
        sideOffset={sideOffset}
        align={align}
        alignOffset={alignOffset}
        anchor={anchor}
        className="isolate z-50"
      >
        <ComboboxPrimitive.Popup
          data-slot="combobox-content"
          className={cn(
            "group/combobox-content relative max-h-96 w-[min(20rem,var(--available-width))] min-w-[16rem] origin-(--transform-origin) overflow-hidden rounded-md border border-[var(--border)] bg-[var(--panel)] text-[var(--foreground)] shadow-lg outline-none",
            "*:data-[slot=input-group]:m-1 *:data-[slot=input-group]:mb-0",
            className,
          )}
          {...props}
        />
      </ComboboxPrimitive.Positioner>
    </ComboboxPrimitive.Portal>
  );
}

function ComboboxList({ className, ...props }: ComboboxPrimitive.List.Props) {
  return (
    <ComboboxPrimitive.List
      data-slot="combobox-list"
      className={cn(
        "max-h-56 scroll-py-1 overflow-y-auto p-1 data-empty:p-0",
        className,
      )}
      {...props}
    />
  );
}

function ComboboxItem({
  className,
  children,
  ...props
}: ComboboxPrimitive.Item.Props) {
  return (
    <ComboboxPrimitive.Item
      data-slot="combobox-item"
      className={cn(
        "relative flex w-full cursor-default flex-col items-start gap-0.5 rounded-sm px-2 py-1.5 text-sm outline-hidden select-none",
        "data-highlighted:bg-[color-mix(in_srgb,var(--gold)_16%,transparent)] data-highlighted:text-[var(--foreground)]",
        "data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
        className,
      )}
      {...props}
    >
      {children}
      <ComboboxPrimitive.ItemIndicator
        data-slot="combobox-item-indicator"
        className="pointer-events-none absolute top-2 right-2 flex size-4 items-center justify-center"
      >
        <CheckIcon className="size-3.5 text-[var(--gold)]" />
      </ComboboxPrimitive.ItemIndicator>
    </ComboboxPrimitive.Item>
  );
}

function ComboboxEmpty({ className, ...props }: ComboboxPrimitive.Empty.Props) {
  return (
    <ComboboxPrimitive.Empty
      data-slot="combobox-empty"
      className={cn(
        "hidden w-full justify-center py-3 text-center text-xs text-[var(--muted)] group-data-empty/combobox-content:flex",
        className,
      )}
      {...props}
    />
  );
}

function ComboboxStatus({
  className,
  ...props
}: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="combobox-status"
      role="status"
      aria-live="polite"
      className={cn("px-2 py-1.5 text-[10px] text-[var(--muted)]", className)}
      {...props}
    />
  );
}

export {
  Combobox,
  ComboboxInput,
  ComboboxContent,
  ComboboxList,
  ComboboxItem,
  ComboboxEmpty,
  ComboboxTrigger,
  ComboboxValue,
  ComboboxStatus,
};
