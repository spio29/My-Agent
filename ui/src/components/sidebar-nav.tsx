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

const normalizePathPrefix = (value: string | undefined): string => {
  const trimmed = String(value || "").trim();
  if (!trimmed || trimmed === "/") {
    return "";
  }

  return `/${trimmed.replace(/^\/+|\/+$/g, "")}`;
};

const APP_BASE_PATH = normalizePathPrefix(process.env.NEXT_PUBLIC_BASE_PATH);

const navItems = [
  { href: "/", label: "Overview", icon: LayoutDashboard },
  { href: "/influencers", label: "Influencers", icon: UsersRound },
  { href: "/workflows", label: "Workflows", icon: Workflow },
  { href: "/runs", label: "Runs", icon: PlaySquare },
  { href: "/incidents", label: "Incidents", icon: AlertTriangle },
  { href: "/settings", label: "Settings", icon: Settings2 },
];

export default function SidebarNav() {
  const pathname = usePathname();
  const normalizedPathname =
    APP_BASE_PATH && (pathname === APP_BASE_PATH || pathname.startsWith(`${APP_BASE_PATH}/`))
      ? pathname.slice(APP_BASE_PATH.length) || "/"
      : pathname;

  return (
    <nav
      aria-label="Primary"
      className="no-scrollbar flex flex-nowrap gap-2 overflow-x-auto pb-1 lg:flex-col lg:gap-1.5 lg:overflow-visible lg:pb-0"
    >
      {navItems.map((item) => {
        const Icon = item.icon;
        const isActive = normalizedPathname === item.href;
        const itemClassName = cn(
          "flex shrink-0 items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors",
          isActive
            ? "bg-slate-900 text-white"
            : "text-slate-700 hover:bg-white hover:text-slate-950",
        );

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
