import { ReactNode } from "react";

import { cn } from "@/lib/utils";

type StatusTone = "neutral" | "info" | "success" | "warning" | "critical";

const toneClassName: Record<StatusTone, string> = {
  neutral: "border-stone-700 bg-stone-900/70 text-stone-300",
  info: "border-lime-800 bg-lime-950/60 text-lime-300",
  success: "border-emerald-800 bg-emerald-950/60 text-emerald-300",
  warning: "border-amber-800 bg-amber-950/60 text-amber-300",
  critical: "border-rose-900 bg-rose-950/60 text-rose-300",
};

type StatusPillProps = {
  children: ReactNode;
  tone?: StatusTone;
  className?: string;
};

export default function StatusPill({
  children,
  tone = "neutral",
  className,
}: StatusPillProps) {
  return (
    <span
      className={cn(
        "status-pill inline-flex items-center rounded-[8px] border px-2 py-1 text-xs font-medium",
        toneClassName[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
