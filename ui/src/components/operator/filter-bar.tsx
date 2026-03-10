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
    <div className={cn("filter-bar flex flex-wrap gap-2", className)}>
      {items.map((item) => {
        const isActive = item.value === value;

        return (
          <button
            key={item.value}
            type="button"
            onClick={() => onChange(item.value)}
            className={cn(
              "filter-chip inline-flex items-center gap-2 rounded-[8px] border px-3 py-1.5 text-sm transition-colors",
              isActive
                ? "border-stone-500 bg-stone-200 text-stone-950"
                : "border-stone-700 bg-stone-950/40 text-stone-300 hover:bg-stone-900/80",
            )}
          >
            <span>{item.label}</span>
            {typeof item.count === "number" ? (
              <span className={cn("text-xs", isActive ? "text-stone-700" : "text-stone-500")}>
                {item.count}
              </span>
            ) : null}
          </button>
        );
      })}
    </div>
  );
}
