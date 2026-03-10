"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  AlertTriangle,
  LayoutDashboard,
  PlaySquare,
  Settings2,
  UsersRound,
  Workflow,
} from "lucide-react";

import { cn } from "@/lib/utils";

const navItems = [
  { href: "/", label: "Overview", icon: LayoutDashboard, available: true },
  { href: "/influencers", label: "Influencers", icon: UsersRound, available: false },
  { href: "/workflows", label: "Workflows", icon: Workflow, available: false },
  { href: "/runs", label: "Runs", icon: PlaySquare, available: true },
  { href: "/incidents", label: "Incidents", icon: AlertTriangle, available: false },
  { href: "/settings", label: "Settings", icon: Settings2, available: true },
];

export default function SidebarNav() {
  const pathname = usePathname();

  return (
    <nav
      aria-label="Primary"
      className="no-scrollbar flex flex-nowrap gap-2 overflow-x-auto pb-1 lg:flex-col lg:gap-1.5 lg:overflow-visible lg:pb-0"
    >
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = pathname === item.href;
        const itemClassName = cn(
          "flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
          isActive
            ? "bg-slate-900 text-white"
            : item.available
              ? "text-slate-700 hover:bg-white hover:text-slate-950"
              : "text-slate-400",
        );

        if (!item.available) {
          return (
            <span key={item.href} aria-disabled="true" className={itemClassName}>
              <Icon className="h-4 w-4" />
              <span>{item.label}</span>
            </span>
          );
        }

        return (
          <Link key={item.href} href={item.href} className={itemClassName}>
            <Icon className="h-4 w-4" />
            <span>{item.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
