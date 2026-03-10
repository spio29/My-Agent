"use client";

import { type ReactNode, useEffect } from "react";
import { X } from "lucide-react";

import StatusPill from "@/components/operator/status-pill";

type DrawerField = {
  label: string;
  value: string;
};

type DrawerSection = {
  title: string;
  body: string[];
};

type DetailDrawerProps = {
  open: boolean;
  title: string;
  subtitle?: string;
  statusLabel?: string;
  statusTone?: "neutral" | "info" | "success" | "warning" | "critical";
  fields?: DrawerField[];
  sections?: DrawerSection[];
  footer?: ReactNode;
  onClose: () => void;
};

export default function DetailDrawer({
  open,
  title,
  subtitle,
  statusLabel,
  statusTone = "neutral",
  fields = [],
  sections = [],
  footer,
  onClose,
}: DetailDrawerProps) {
  useEffect(() => {
    if (!open) return;

    const previousOverflow = document.body.style.overflow;
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        onClose();
      }
    };

    document.body.style.overflow = "hidden";
    window.addEventListener("keydown", handleKeyDown);

    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [open, onClose]);

  if (!open) return null;

  return (
    <>
      <div className="fixed inset-0 z-40 bg-slate-900/20" onClick={onClose} />
      <aside
        aria-label="Operator detail"
        className="fixed inset-y-0 right-0 z-50 flex w-full max-w-md flex-col border-l border-slate-200 bg-white shadow-[0_8px_30px_rgba(15,23,42,0.16)]"
        role="complementary"
      >
        <div className="flex items-start justify-between gap-4 border-b border-slate-200 px-5 py-4">
          <div>
            <h2 className="text-lg font-semibold tracking-[-0.02em] text-slate-950">
              Operator detail
            </h2>
            {subtitle ? <p className="mt-1 text-sm text-slate-500">{subtitle}</p> : null}
            <p className="mt-2 text-sm leading-6 text-slate-700">{title}</p>
          </div>
          <button
            aria-label="Close detail"
            className="rounded-md border border-slate-200 p-2 text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-700"
            type="button"
            onClick={onClose}
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="flex-1 space-y-5 overflow-y-auto px-5 py-4">
          {statusLabel ? <StatusPill tone={statusTone}>{statusLabel}</StatusPill> : null}

          {fields.length > 0 ? (
            <dl className="grid gap-3 sm:grid-cols-2">
              {fields.map((field) => (
                <div key={field.label} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-3">
                  <dt className="text-sm text-slate-500">{field.label}</dt>
                  <dd className="mt-1 text-sm font-medium text-slate-900">{field.value}</dd>
                </div>
              ))}
            </dl>
          ) : null}

          {sections.map((section) => (
            <section key={section.title} className="space-y-2">
              <h3 className="text-sm font-semibold text-slate-900">{section.title}</h3>
              <div className="space-y-2 text-sm leading-6 text-slate-600">
                {section.body.map((paragraph, index) => (
                  <p key={`${section.title}-${index}`}>{paragraph}</p>
                ))}
              </div>
            </section>
          ))}
        </div>

        {footer ? <div className="border-t border-slate-200 px-5 py-4">{footer}</div> : null}
      </aside>
    </>
  );
}
