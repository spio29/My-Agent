import { ReactNode } from "react";

import { cn } from "@/lib/utils";

type SectionShellProps = {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  contentClassName?: string;
};

export default function SectionShell({
  title,
  description,
  actions,
  children,
  className,
  contentClassName,
}: SectionShellProps) {
  return (
    <section className={cn("workspace-panel rounded-[10px] border", className)}>
      <div className="workspace-panel__head flex flex-col gap-3 px-5 py-4 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-lg font-semibold tracking-[-0.02em] text-slate-950">{title}</h3>
          {description ? (
            <p className="mt-1 text-sm leading-6 text-slate-600">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="workspace-panel__actions flex flex-wrap items-center gap-2">
            {actions}
          </div>
        ) : null}
      </div>
      <div className={cn("workspace-panel__body px-5 py-4", contentClassName)}>{children}</div>
    </section>
  );
}
