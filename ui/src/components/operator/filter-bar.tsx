"use client";

import { cn } from "@/lib/utils";

export type FilterItem = {
  label: string;
  value: string;
  count?: number;
};

type FilterBarProps = {
  items: FilterItem[];
  value: string;
  onChange: (value: string) => void;
  className?: string;
};

export default function FilterBar({
  items,
  value,
  onChange,
  className,
}: FilterBarProps) {
  return (
    <div className={cn("flex flex-wrap gap-2", className)}>
      {items.map((item) => {
        const isActive = item.value === value;

        return (
          <button
            key={item.value}
            type="button"
            onClick={() => onChange(item.value)}
            className={cn(
              "inline-flex items-center gap-2 rounded-md border px-3 py-1.5 text-sm transition-colors",
              isActive
                ? "border-slate-900 bg-slate-900 text-white"
                : "border-slate-200 bg-white text-slate-700 hover:bg-slate-50",
            )}
          >
            <span>{item.label}</span>
            {typeof item.count === "number" ? (
              <span className={cn("text-xs", isActive ? "text-slate-300" : "text-slate-500")}>
                {item.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
