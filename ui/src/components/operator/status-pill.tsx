import { ReactNode } from "react";

import { cn } from "@/lib/utils";

type StatusTone = "neutral" | "info" | "success" | "warning" | "critical";

const toneClassName: Record<StatusTone, string> = {
  neutral: "border-slate-200 bg-slate-100 text-slate-700",
  info: "border-stone-300 bg-stone-100 text-stone-700",
  success: "border-emerald-200 bg-emerald-50 text-emerald-700",
  warning: "border-amber-200 bg-amber-50 text-amber-700",
  critical: "border-rose-200 bg-rose-50 text-rose-700",
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
        "inline-flex items-center rounded-md border px-2 py-1 text-xs font-medium",
        toneClassName[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
